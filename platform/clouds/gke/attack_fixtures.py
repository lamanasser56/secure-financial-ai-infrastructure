"""Run-owned synthetic rows, cleaned by the same owner-only psql path as make seed-demo."""
import base64
from decimal import Decimal
import json
import uuid

from attack_fixture_spec import MONTH, ENTRIES
from attack_runtime import NotExercised, RestoreFailed


def session_user(session):
    body=session[0].split('=',1)[1].split('.')[0]
    user=json.loads(base64.urlsafe_b64decode(body+'='*(-len(body)%4)))['u']
    return str(uuid.UUID(user))


class FixtureRows:
    def __init__(self,k,app):
        self.k,self.app=k,app
        self.tag='attack-fixture:'+uuid.uuid4().hex
        self.rows=[]; self.sessions={}

    def prepare(self):
        self.sessions={name:self.app.login(name) for name in ('lama','sara')}
        for session in self.sessions.values():
            status,body,_=self.app.call('GET','/api/expenses?month='+MONTH,cookie=session[0])
            if status!=200 or not isinstance(body,dict) or body.get('expenses')!=[]:
                raise NotExercised('reserved_fixture_month_not_empty_or_unavailable')
        for name,day,merchant,category,amount in ENTRIES:
            entry={'spent_on':MONTH+'-'+day,'merchant':merchant,'category':category,'amount':amount,'note':self.tag}
            row={'user':session_user(self.sessions[name]),'entry':entry,'id':None}
            self.rows.append(row)  # Record intent BEFORE sending: an interrupted response can follow a committed insert.
            status,body,_=self.app.call('POST','/api/expenses',entry,*self.sessions[name])
            if status!=201 or not isinstance(body,dict) or type(body.get('id')) is not int or body['id']<=0:
                raise NotExercised('fixture_insert_incomplete')
            row['id']=body['id']
        return True,{'rows_created':len(self.rows),'month':MONTH}

    def attempt_cross_user_insert(self, session, other):
        # A deliberately invalid POST can still commit if the boundary regresses. Own that
        # row before sending, whether a broken handler chooses the caller or supplied user.
        entry={'spent_on':MONTH+'-04','merchant':'Owner scope probe','category':'food',
               'amount':'1.00','note':self.tag}
        for user in {session_user(session),session_user(other)}:
            self.rows.append({'user':user,'entry':entry,'id':None})
        return self.app.call('POST','/api/expenses',dict(entry,user_id=session_user(other)),*session)[0]

    def cleanup_sql(self):
        quote=lambda value:"'"+str(value).replace("'","''")+"'"
        statements=['\\set ON_ERROR_STOP on','BEGIN;']
        for row in self.rows:
            entry=row['entry']
            where=' AND '.join((
                'user_id='+quote(row['user'])+'::uuid','spent_on='+quote(entry['spent_on'])+'::date',
                'merchant='+quote(entry['merchant']),'category='+quote(entry['category']),
                'amount_minor='+str(int(Decimal(entry['amount'])*100)),'note='+quote(self.tag)))
            if row['id'] is not None: where+=' AND id='+str(row['id'])
            check='n>1'
            if row['id'] is not None:
                check+=' OR (n=0 AND EXISTS(SELECT 1 FROM finance.expenses WHERE id='+str(row['id'])+'))'
            statements.append("DO $cleanup$ DECLARE n integer; BEGIN DELETE FROM finance.expenses WHERE "+where+
                "; GET DIAGNOSTICS n=ROW_COUNT; IF "+check+" THEN RAISE EXCEPTION 'fixture_ownership_changed'; END IF; END $cleanup$;")
        statements.append("DO $remaining$ BEGIN IF EXISTS(SELECT 1 FROM finance.expenses WHERE note="+quote(self.tag)+
            ") THEN RAISE EXCEPTION 'fixture_cleanup_incomplete'; END IF; END $remaining$;")
        statements+=['COMMIT;','SELECT 1;']
        return '\n'.join(statements)+'\n'

    def cleanup(self):
        if self.rows:
            result=self.k('-n','platform','exec','-i','postgres-0','--','psql','-U','postgres','-d','finance',
                '-X','-q','-A','-t','-v','ON_ERROR_STOP=1',input=self.cleanup_sql())
            if result.returncode or result.stdout.strip()!='1':
                raise RestoreFailed('fixture_cleanup_incomplete')
        count=len(self.rows); self.rows=[]
        return True,{'fixture_intents_cleaned':count}
