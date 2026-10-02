# Secret delivery contracts

Every file here is a non-deployable example with invalid placeholder metadata or values. No Kustomization includes this directory. Real values must be delivered outside Git by an approved secret manager with separate runtime, migration and gateway identities.

- [LiteLLM key](litellm-master-key.secret.example.yaml)
- [Runtime database credential](runtime-database.secret.example.yaml)
- [Migration database credential](migration-database.secret.example.yaml)

The runtime role must not own tables or bypass RLS. The migration role owns schema changes but is not used by a long-running application. Neither role receives the LiteLLM master key or cloud provider identity.
