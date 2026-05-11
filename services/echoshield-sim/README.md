# EchoShield Simulator

Anti-drone radar simulator for the CICS-TAK PoC. Consumes Map Sim `GET /objects` at
10 Hz, applies Gaussian noise + azimuth/elevation geometry, and broadcasts NDJSON
`RadarTrack` records over plain TCP.

See [`specs/003-echoshield-sim/quickstart.md`](../../specs/003-echoshield-sim/quickstart.md)
for end-to-end setup.

## Endpoints

- **Upstream**: `GET {map_sim_url}/objects?lat=&lon=&radius_m=` — defaults to
  `http://localhost:18090`.
- **Downstream**: `tcp://{feed_host}:{feed_port}` NDJSON — defaults to `0.0.0.0:9000`;
  see [`contracts/tcp-feed.md`](../../specs/003-echoshield-sim/contracts/tcp-feed.md).

## Install

```bash
cd services/echoshield-sim
pip install -e '.[dev]'
```

## Run

```bash
echoshield-sim --config config/local.yaml
# or
python -m echoshield_sim --config config/local.yaml --seed 42 --verbose
```

## Structured log events

| event                 | keys                                                  |
| --------------------- | ----------------------------------------------------- |
| `startup`             | `map_sim_url`, `feed`, `seed`                         |
| `tcp_server_listening`| `host`, `port`                                        |
| `client_connected`    | `remote_addr`, `client_count`                         |
| `client_disconnected` | `remote_addr`, `client_count`, `reason`               |
| `map_sim_query`       | `tick_id`, `latency_ms`, `count`, `status_code`       |
| `map_sim_unavailable` | `reason` (throttled to ≤1/s)                          |
| `track_lifecycle`     | `drone_id`, `track_id`, `event` (`active|lost|recover`)|
| `tick_overrun`        | `tick_id`, `reason`                                   |
