# FrigoCore

Cloud-native IoT Platform for Refrigeration Monitoring and Industrial Automation.

## Overview

FrigoCore is an enterprise-grade IoT platform designed for real-time refrigeration monitoring, predictive maintenance, and industrial automation. Built on a modern microservices architecture, it provides robust data ingestion, processing, and visualization capabilities for cold chain management.

## Tech Stack

### Backend
- **Python 3.13** — core application language
- **FastAPI** — high-performance REST API framework
- **SQLAlchemy 2** — async ORM for database interactions
- **Alembic** — database schema migrations
- **PostgreSQL** — primary relational database
- **Redis** — caching and message broker
- **EMQX** — MQTT broker for IoT device communication
- **Docker** — containerized deployment

### Frontend
- **Vue 3** — progressive UI framework
- **TypeScript** — type-safe development
- **Pinia** — state management
- **Vite** — fast build tooling
- **TailwindCSS** — utility-first CSS framework

## Project Structure

```
FrigoCore/
├── backend/           # FastAPI application
├── frontend/          # Vue 3 SPA
├── gateway-sdk/       # API Gateway SDK
├── docs/              # Documentation
├── docker/            # Docker configurations
├── deployments/       # Deployment manifests
├── scripts/           # Utility scripts
├── tests/             # Integration & E2E tests
├── .github/           # CI/CD workflows
├── .gitignore
├── README.md
└── docker-compose.yml
```

## Getting Started

### Prerequisites

- Docker & Docker Compose
- Python 3.13+
- Node.js 20+
- Git

### Quick Start

```bash
# Clone the repository
git clone https://github.com/Janszuszu/FrigoCore.git
cd FrigoCore

# Start all services
docker compose up -d
```

### Services

| Service      | Port  | Description                |
|-------------|-------|----------------------------|
| API         | 8000  | FastAPI backend            |
| Frontend    | 5173  | Vue 3 development server   |
| PostgreSQL  | 5432  | Primary database           |
| Redis       | 6379  | Cache & message broker     |
| EMQX        | 1883  | MQTT broker (TCP)          |
| EMQX HTTP   | 8083  | MQTT WebSocket             |
| EMQX Dashboard | 18083 | EMQX management console |

## License

Proprietary. All rights reserved.