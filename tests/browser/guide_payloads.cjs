// Current Guide composition; only model/redactor transports are scripted. No external requests.
const path = require('node:path');
const root = path.resolve(__dirname, '../..'), base = path.join(root, 'platform/agents/platform-guide');
const {build} = require(path.join(base, 'tools/build-index'));
const {DocsIndex} = require(path.join(base, 'src/search'));
const {Guide} = require(path.join(base, 'src/agent'));
const {Redactor, Gateway} = require(path.join(base, 'src/clients'));
const {fakes} = require(path.join(base, 'test/helpers'));

(async () => {
  const index = new DocsIndex(build(path.join(root, 'docs'), path.join(base, 'current-docs.json'), {sourceCommit: 'e'.repeat(40)}));
  const transports = fakes({replies: [{action: 'answer', sources: ['p1']}, {action: 'answer', sources: ['p1']},
    {action: 'answer', text: 'All personal information is masked.'}]});
  const guide = new Guide({index, stream: {write() {}}, redactor: new Redactor('k'.repeat(64), {transport: transports.redactorTransport}),
    gateway: new Gateway('synthetic-guide-key', {transport: transports.gatewayTransport})});
  const en = await guide.ask('What does the Model gateway mask?', 'en');
  const ar = await guide.ask('ما الذي تخفيه بوابة النموذج؟', 'ar');
  const refused = await guide.ask('zzzzqqqq', 'en');
  const blocked = await guide.ask('What does the Model gateway mask?', 'en');
  if (en.status !== 'answered' || ar.status !== 'answered' || refused.reason !== 'not_covered' || blocked.reason !== 'unsupported_answer') throw new Error('current Guide fixture composition failed');
  if (!ar.sources.every(source => /[\u0600-\u06ff]/.test(source.excerpt))) throw new Error('Arabic source retrieval required');
  process.stdout.write(JSON.stringify({info: guide.info(), en, ar, refused, blocked}));
})().catch(error => { process.stderr.write(error.stack); process.exitCode = 1; });
