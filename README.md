# glpi-testbed
> **This project was generated with the assistance of Claude (Anthropic).** The compose generator, container architecture, and auto-install logic were designed and debugged in collaboration with Claude Code.

A local testing environment that runs 16 GLPI versions simultaneously as isolated containers, each fully installed and ready to use with no manual setup required. Covers GLPI 10.0.18–10.0.25 and 11.0.0–11.0.7. Images are pulled directly from the official [glpi/glpi](https://hub.docker.com/r/glpi/glpi) repository on Docker Hub.

Every instance auto-installs its database on first start and is accessible on a predictable localhost port within about 60–90 seconds.

## Requirements

### Software

- **Podman 4.4+** with the `podman compose` subcommand
- **Python 3** with `pyyaml` — only needed to regenerate `docker-compose.yml`
  ```bash
  pip install pyyaml
  ```

### Hardware

All 32 containers running simultaneously consume approximately:

| | Per container | 16 containers |
|---|---|---|
| GLPI (Apache + PHP) | ~84 MB RAM | ~1.3 GB RAM |
| MySQL 8.0 | ~539 MB RAM | ~8.4 GB RAM |
| **Total** | | **~9.7 GB RAM** |

- **RAM:** 12 GB free recommended (10 GB used by containers, 2 GB headroom for the OS)
- **Disk:** ~17 GB for container images (16 GLPI images × ~1 GB each + one shared MySQL 8.0 image at ~820 MB) + ~5 GB for volume data after installation

> If RAM is limited, you can start a subset of instances:
> ```bash
> podman compose up -d glpi_11_0_7 mysql_11_0_7  # start only GLPI 11.0.7 and its database
> ```

## Usage

```bash
# Pull all images (one-time, ~17 GB)
podman compose pull

# Start all 32 containers
podman compose up -d

# Stop all containers (data is preserved in volumes)
podman compose down

# Watch installation progress on a specific version
podman logs -f glpi_10_0_18

# Check status of all containers
podman compose ps
```

Allow 60–90 seconds after `up -d` for all instances to finish installing.

### Adding a version

Sync automatically with Docker Hub (detects and adds any missing patch versions):

```bash
python3 update-versions.py

# new containers start; existing ones are unaffected
podman compose up -d
```

Or manually: append the patch number to `VERSIONS_10X` / `VERSIONS_11X` in `generate-compose.py`, then regenerate:

```bash
# Edit generate-compose.py:
#   VERSIONS_10X = [..., 26]
#   VERSIONS_11X = [..., 8]

# overwrite the generated file
python3 generate-compose.py > docker-compose.yml

# new containers start; existing ones are unaffected
podman compose up -d
```

### Resetting an instance

Wipe a single version and reinstall from scratch:

```bash
# stop the two containers
podman compose stop glpi_10_0_20 mysql_10_0_20

# remove them
podman compose rm -f glpi_10_0_20 mysql_10_0_20

# wipe their data volumes
podman volume rm glpi_glpi_data_10_0_20 glpi_mysql_data_10_0_20

# recreate and reinstall
podman compose up -d glpi_10_0_20
```

Wipe everything and start over:

```bash
# stop and remove all containers
podman compose down

# delete all data volumes
podman volume ls --format '{{.Name}}' | grep '^glpi_' | xargs podman volume rm

# recreate all 32 containers
podman compose up -d
```

## Instance table

| GLPI version | URL | Credentials |
|---|---|---|
| 10.0.18 | http://localhost:10018 | glpi / glpi |
| 10.0.19 | http://localhost:10019 | glpi / glpi |
| 10.0.20 | http://localhost:10020 | glpi / glpi |
| 10.0.21 | http://localhost:10021 | glpi / glpi |
| 10.0.22 | http://localhost:10022 | glpi / glpi |
| 10.0.23 | http://localhost:10023 | glpi / glpi |
| 10.0.24 | http://localhost:10024 | glpi / glpi |
| 10.0.25 | http://localhost:10025 | glpi / glpi |
| 11.0.0  | http://localhost:11000 | glpi / glpi |
| 11.0.1  | http://localhost:11001 | glpi / glpi |
| 11.0.2  | http://localhost:11002 | glpi / glpi |
| 11.0.3  | http://localhost:11003 | glpi / glpi |
| 11.0.4  | http://localhost:11004 | glpi / glpi |
| 11.0.5  | http://localhost:11005 | glpi / glpi |
| 11.0.6  | http://localhost:11006 | glpi / glpi |
| 11.0.7  | http://localhost:11007 | glpi / glpi |

Port formula: `major * 1000 + patch` — e.g. 10.0.18 → 10018, 11.0.7 → 11007.

## Project file architecture

```
glpi-testbed/
├── generate-compose.py     version configuration and compose generator
├── docker-compose.yml      generated output — do not edit directly
├── update-versions.py      syncs GLPI versions from Docker Hub, updates all three files above
├── .github/
│   └── workflows/
│       └── update-glpi-versions.yml  opens a PR automatically every Monday when new versions appear
└── README.md               this file
```

### `generate-compose.py`

The single source of truth for the entire environment. It contains the version lists (`VERSIONS_10X`, `VERSIONS_11X`), database credentials, and MySQL healthcheck parameters. Running it produces a complete `docker-compose.yml`.

To change anything about how containers are configured — ports, credentials, MySQL version, healthcheck timing — edit this file and regenerate.

### `docker-compose.yml`

Generated output from `generate-compose.py`. Defines all 32 services (16 GLPI + 16 MySQL), 32 named volumes, and 16 isolated bridge networks. Commit this file so the environment can be reproduced without Python or pyyaml.

## Container architecture

Each GLPI version runs as an isolated, self-contained stack:

```
┌─────────────────────────────────────┐
│  glpi_net_10_0_18  (bridge network) │
│                                     │
│      ┌───────────────────┐          │
│      │ glpi_mysql_10_0_18│          │
│      │  mysql:8.0        │          │
│      │  port 3306        │          │
│      │  healthcheck      │          │
│      └────────┬──────────┘          │
│               │ depends_on: healthy │
│               ▼                     │
│      ┌───────────────────┐          │
│      │  glpi_10_0_18     │          │
│      │  glpi/glpi:10.0.18│          │
│      │  port → 10018:80  │          │
│      └───────────────────┘          │
└─────────────────────────────────────┘
           × 16 versions
```

**Isolation:** each pair shares a dedicated bridge network. No GLPI container can reach another version's MySQL, and no two instances share any data.

**Startup sequence:**

1. MySQL container starts and initialises its data directory
2. MySQL healthcheck (`mysqladmin ping`) passes after the server is ready
3. `depends_on: condition: service_healthy` releases the GLPI container
4. GLPI's built-in startup script creates data directories, runs `database:install` via the CLI, then starts Apache (10.x) or supervisord (11.x)
5. The login page is served at `http://localhost:<port>`

**Persistence:** named Docker volumes keep data across `podman compose down / up` cycles. Only `podman volume rm` clears them.

**Networking:** all ports are bound to `127.0.0.1` — instances are accessible only from localhost.

**Auto-install mechanism:** the official `glpi/glpi` images include a startup script that runs `php bin/console database:install` automatically when the database is not yet initialised. `GLPI_SKIP_AUTOUPDATE=true` is set on all instances to prevent automatic schema migrations on restart.
