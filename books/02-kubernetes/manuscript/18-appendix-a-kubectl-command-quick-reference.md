# Appendix A - kubectl Command Quick Reference {#appA}

The commands below are the working set this book used, grouped the way memory works: by task. Flags shown are the ones worth memorizing; `kubectl command --help` is the honest full reference, and `kubectl explain resource.spec.field` reads the schema without leaving the shell.

| Command | Purpose |
| -------------------------- | ------------------------ |
| `kubectl get pods -A -o wide` | All Pods across namespaces with node and IP |
| `kubectl get deploy,rs,svc -n prod` | Several kinds in one call |
| `kubectl describe pod NAME` | Events, conditions, probe results, the debugging front door |
| `kubectl get events --sort-by=.lastTimestamp` | Chronological cluster flight recorder |
| `kubectl get pod NAME -o yaml` | Full declared state; diff against `git` when confused |
| `kubectl explain deployment.spec.strategy` | Schema self-documentation |
| `kubectl top pods / nodes` | Live resource usage (`metrics-server`) |
| `kubectl api-resources` | Every kind, its short name, and its API group |

: Table A.1 - Reading state and resources

| Command | Purpose |
| -------------------------- | ------------------------ |
| `kubectl apply -f dir/ -R` | Apply a manifest tree recursively |
| `kubectl diff -f manifest.yaml` | Server-side dry-run diff before applying |
| `kubectl apply --server-side -f manifest.yaml` | Server-side apply with field ownership |
| `kubectl scale deploy/api --replicas=5` | Imperative replica change (avoid in GitOps estates) |
| `kubectl set image deploy/api api=myorg/api:1.5.0` | Quick image bump for tests |
| `kubectl rollout status deploy/api` | Watch a rollout to completion |
| `kubectl rollout history / undo deploy/api` | Revision list / roll back |
| `kubectl rollout restart deploy/api` | Rolling restart via annotation change |
| `kubectl delete -f manifest.yaml --cascade=foreground` | Delete with owner-aware garbage collection |

: Table A.2 - Changing state

| Command | Purpose |
| -------------------------- | ------------------------ |
| `kubectl logs -f pod/NAME -c container` | Follow container logs; `-p` for the previous crashed instance |
| `kubectl exec -it pod/NAME -- sh` | Shell into a running container |
| `kubectl port-forward svc/api 8080:8080` | Tunnel a `Service` to your laptop |
| `kubectl auth can-i --list --as=SUBJECT` | Effective RBAC for any identity |
| `kubectl config get-contexts / use-context` | List and switch clusters |
| `kubectl config set-context --current --namespace=prod` | Set a default namespace per context |
| `kubectl drain node / uncordon node` | Node maintenance entry and exit |
| `kubectl cordon node` | Mark unschedulable without evicting |

: Table A.3 - Debugging and access

| Command | Purpose |
| -------------------------- | ------------------------ |
| `helm repo add NAME URL` && `helm repo update` | Register and refresh a chart repository |
| `helm upgrade --install REL CHART -f values.yaml -n NS` | Idempotent install or upgrade |
| `helm list -A / helm history REL` | Releases across namespaces / revision list |
| `helm get values REL -n NS` | Values currently in effect |
| `helm rollback REL REV -n NS` | Return to a previous revision |
| `helm template REL CHART -f values.yaml` | Render locally; pairs well with `kubectl diff` |

: Table A.4 - Helm essentials
