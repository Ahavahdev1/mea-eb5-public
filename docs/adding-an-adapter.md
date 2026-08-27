# Adding an Adapter

An adapter bridges the benchmark runner to the system being evaluated. It must
implement the `mea_eb5.adapters.base.AgentAdapter` protocol:

- `describe() -> AdapterDescription`
- `prepare(config) -> None`
- `run(task, workspace, event_sink) -> AdapterExecution`
- `cancel(reason) -> None`

## Rules

1. Never execute shell-interpolated strings from the task instruction.
2. Pass the goal through a file (`--goal-file`) or JSON body.
3. Do not include credentials in event payloads.
4. Terminate the entire process group on timeout or cancel.
5. Report timeouts, protocol errors, and invalid responses honestly.

## Official MEA adapter

Use `mea.adapter.example.yaml` and the digest-pinned
`ContainerCliAdapter`. It adds `--goal-file` itself and enforces the Docker
isolation policy. `CliAdapter` requires `allow_host_execution: true` and is
reserved for local contract tests; it is not the release path.

The HTTP adapter is a library contract and is not exposed by the release CLI.
