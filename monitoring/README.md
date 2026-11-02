# Cluster monitoring (Managed Service for Prometheus)

An optional add-on for a running platform cluster. The cluster already runs Google Managed Service for Prometheus
(`managed_prometheus { enabled = true }` in the Terraform module), but nothing is scraped: the platform's own services
expose only `/healthz`, and every managed namespace is default-deny. `kubelet-scraping.yaml` turns on GKE's built-in
kubelet and cAdvisor scraping, which gives node, Pod and container CPU, memory, disk and volume metrics in Cloud
Monitoring as PromQL-queryable series.

What it does not change: no NetworkPolicy (kubelet targets are node endpoints, and `gmp-system` has no policy), no
Terraform, IAM, RBAC, admission, release lock or new Pod (the existing `gmp-system/collector` does the scraping). It is
not part of `make up`; the cluster's teardown removes it with the cluster.

## Apply

From the repository root, with the repo-pinned kubectl from `make tools` and the kubeconfig `make up` wrote:

```sh
K=.cache/platform-tools/kubectl
KC="${AGENT_PLATFORM_STATE_DIR:-.cache/operator-state}/kubeconfig"
"$K" --kubeconfig "$KC" config current-context   # confirm the intended cluster first
"$K" --kubeconfig "$KC" -n gmp-public patch operatorconfig config --type merge --patch-file monitoring/kubelet-scraping.yaml
"$K" --kubeconfig "$KC" -n gmp-public get operatorconfig config -o jsonpath='{.collection.kubeletScraping}'
```

The last command prints `{"interval":"30s"}`. Series appear in Cloud Monitoring within a few minutes.

## Roll back

```sh
"$K" --kubeconfig "$KC" -n gmp-public patch operatorconfig config --type merge -p '{"collection":{"kubeletScraping":null}}'
```

Collection stops at once; samples already written age out under Cloud Monitoring's retention.

## Example queries

In Cloud Monitoring, Metrics Explorer, switch the query editor to PromQL:

| Question | PromQL |
| --- | --- |
| Scrape targets up (kubelet `:metrics` and `:cadvisor`) | `up{job="kubelet"}` |
| Container memory (working set) by Pod | `sum by (namespace, pod) (container_memory_working_set_bytes{container!=""})` |
| Container CPU cores by Pod | `sum by (namespace, pod) (rate(container_cpu_usage_seconds_total{container!=""}[5m]))` |
| Container filesystem usage | `sum by (namespace, pod) (container_fs_usage_bytes{container!=""})` |
| Persistent volume fill | `kubelet_volume_stats_used_bytes / kubelet_volume_stats_capacity_bytes` |
| Restarts (present without this add-on) | metric `kubernetes.io/container/restart_count` |

Pod phase and Deployment replica state (kube-state-metrics) are deliberately not included: GKE's managed package needs
a Terraform `monitoring_config` change, and a self-run exporter needs a ClusterRole and a new Pod.

## Cost

Managed Service for Prometheus bills per ingested sample. At a 30 s interval each series costs
2 x 60 x 24 x 30 = 86,400 samples a month. Count the series per scrape with
`sum(scrape_samples_post_metric_relabeling)` (Managed Service for Prometheus needs an exact metric name, so
`count({job=~".+"})` is refused) and price them with the current
[Managed Service for Prometheus pricing](https://cloud.google.com/stackdriver/pricing).

Measured on the one-node platform cluster (2 Nov 2026): about 8,500 series per scrape (cAdvisor 5,808 after GKE's own
relabeling, kubelet 2,666), so roughly 730 million samples a month. That is a real cost for a portfolio cluster: a longer
`interval` lowers it in proportion, and rolling back stops it.
