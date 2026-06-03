# Atlas OS — Skills Catalogue

> A reference catalogue of the capability skills Atlas OS agents can draw on.
> It shows **what the system can do** — the menu of expertise an agent can
> apply when planning and executing work. This is a generic, shareable
> reference: no personal configuration lives here. Anything machine- or
> user-specific is expressed as a `{{PLACEHOLDER}}` token.

This catalogue lists **149 capability skills** across **7 domains**,
plus the **Atlas-native skills** and **scheduled automations** that ship with
the repo — **160+ skills** in total. For *how* skills work (anatomy, lifecycle,
authoring your own), see [**SKILLS-FRAMEWORK.md**](SKILLS-FRAMEWORK.md). For the
scheduled-task skills and their cadences, see
[**SCHEDULED-TASKS.md**](SCHEDULED-TASKS.md).

---

## Contents

- [🔒 Security](#security) — 20 skills
- [⚙️ DevOps](#devops) — 25 skills
- [🎨 Frontend](#frontend) — 20 skills
- [🛠️ Backend](#backend) — 23 skills
- [✅ Quality](#quality) — 20 skills
- [📊 Data & AI](#data--ai) — 21 skills
- [📈 Business](#business) — 20 skills
- [🤖 Atlas-native skills](#atlas-native-skills) — 4 skills
- [⏰ Scheduled automations](#scheduled-automations) — 9 tasks

---

## Security

*20 skills.*

### `security-first`
Security-first mindset for all code decisions.

- **What it does:** Applies a security-by-design lens to every architectural and implementation decision, flagging risk before it compounds.
- **When to use:** Reach for this when starting a new feature or reviewing existing code where security trade-offs have not been explicitly considered.

### `api-security-best-practices`
Secure API design with rate limiting, CORS, and authentication.

- **What it does:** Enforces hardened API patterns including rate limiting, CORS policy, authentication schemes, and input validation across REST and GraphQL surfaces.
- **When to use:** Use when designing or auditing an API endpoint where exposure to untrusted clients, abuse, or misconfigured access control is a concern.

### `owasp-top-10`
OWASP Top 10 vulnerability prevention.

- **What it does:** Maps code and architecture against the current OWASP Top 10, identifying injection, broken access control, misconfiguration, and other critical classes of vulnerability.
- **When to use:** Use during code review, pre-release audit, or any time a web application needs to be assessed against the industry-standard vulnerability taxonomy.

### `penetration-testing`
Penetration testing and vulnerability assessment.

- **What it does:** Structures and executes systematic attack simulations against a target system, documenting findings with severity ratings and remediation steps.
- **When to use:** Reach for this when a system needs adversarial validation before launch, after a significant change, or as part of a scheduled security assessment cycle.

### `authentication-expert`
OAuth, SSO, JWT, and session management patterns.

- **What it does:** Designs and reviews authentication flows covering OAuth 2.0, OpenID Connect, SSO federation, JWT issuance and validation, and secure session lifecycle management.
- **When to use:** Use when building or hardening login, token issuance, or identity federation flows where misconfiguration could lead to account takeover.

### `encryption-specialist`
Encryption algorithms, TLS, and secure key management.

- **What it does:** Selects appropriate cryptographic primitives, configures TLS correctly, and establishes key generation, storage, rotation, and destruction procedures.
- **When to use:** Reach for this when data must be protected at rest or in transit, or when an existing cryptographic implementation needs evaluation against current best practice.

### `security-audit`
Security code review and audit methodology.

- **What it does:** Conducts structured source-code audits using static analysis, manual review, and threat-driven test cases to surface exploitable defects.
- **When to use:** Use when a codebase requires a formal security sign-off, after third-party library updates, or when preparing for an external compliance review.

### `secure-coding`
Input validation, output encoding, and secure defaults.

- **What it does:** Implements defensive coding patterns — validated inputs, context-aware output encoding, fail-closed defaults, and minimal attack surface — across application layers.
- **When to use:** Use at the implementation stage of any feature that handles untrusted input, renders user-supplied content, or exposes system functionality.

### `zero-trust-security`
Zero-trust architecture and least-privilege enforcement.

- **What it does:** Designs access controls on the assumption that no network segment or identity is inherently trusted, enforcing continuous verification and minimal privilege at every layer.
- **When to use:** Reach for this when architecting internal service communication, remote access, or any environment where implicit network trust must be eliminated.

### `secrets-management`
Secrets storage with Vault, environment variables, and rotation.

- **What it does:** Establishes secure workflows for storing, injecting, and rotating secrets using tools such as HashiCorp Vault, cloud secret managers, and environment variable hygiene.
- **When to use:** Use when credentials, API keys, or certificates need to be kept out of source control and delivered safely to running workloads with automated rotation.

### `identity-access-management`
RBAC, IAM policies, and access control patterns.

- **What it does:** Models and implements role-based access control, policy-as-code IAM rules, and attribute-based controls to enforce the principle of least privilege.
- **When to use:** Reach for this when defining who can do what in a system, auditing existing permissions for over-provisioning, or migrating to a policy-driven access model.

### `security-monitoring`
SIEM, intrusion detection, and threat monitoring.

- **What it does:** Instruments systems with logging, alerting, and SIEM integration to detect anomalous behaviour, lateral movement, and indicators of compromise in real time.
- **When to use:** Use when setting up observability for a production environment where early detection of intrusion or abuse is a security requirement.

### `web-application-firewall`
WAF configuration and DDoS protection.

- **What it does:** Configures web application firewall rule sets and rate-limit policies to filter malicious traffic, block common exploits, and absorb volumetric attacks.
- **When to use:** Reach for this when hardening a public-facing web service against automated attack traffic, scrapers, or layer-7 denial-of-service attempts.

### `container-security`
Container hardening and image scanning.

- **What it does:** Applies container-specific security controls including minimal base images, read-only filesystems, non-root execution, capability dropping, and automated CVE scanning.
- **When to use:** Use when building or deploying containerised workloads where image hygiene, runtime privileges, and supply-chain risk need to be systematically controlled.

### `cloud-security`
Cloud security posture management and provider hardening.

- **What it does:** Assesses and remediates cloud configuration across AWS, GCP, and Azure, covering IAM hygiene, public exposure, encryption defaults, and posture management tooling.
- **When to use:** Reach for this when auditing a cloud environment, establishing a security baseline for a new account, or responding to a misconfiguration finding.

### `compliance-frameworks`
SOC 2, GDPR, HIPAA, and PCI-DSS compliance.

- **What it does:** Maps technical and organisational controls to the requirements of major compliance frameworks, identifying gaps and generating evidence artefacts for audit.
- **When to use:** Use when preparing for a formal compliance audit, onboarding a regulated customer, or implementing controls required by a specific regulatory obligation.

### `threat-modeling`
STRIDE and DREAD threat modeling methodologies.

- **What it does:** Applies structured threat modeling frameworks to decompose a system into trust boundaries, enumerate threats, and prioritise mitigations by likelihood and impact.
- **When to use:** Reach for this at the design phase of any new system or significant feature where a systematic enumeration of attack vectors is needed before implementation begins.

### `incident-response`
Incident response, forensics, and breach handling.

- **What it does:** Provides a structured playbook for detecting, containing, eradicating, and recovering from security incidents, including evidence preservation and post-incident review.
- **When to use:** Use when a security event is suspected or confirmed, or when preparing runbooks and team readiness for future incident scenarios.

### `code-signing`
Code signing and certificate management.

- **What it does:** Establishes pipelines for signing build artefacts, managing signing certificates through their lifecycle, and verifying integrity at deployment time.
- **When to use:** Reach for this when software distribution requires tamper-evidence, when supply-chain integrity must be verifiable, or when certificate expiry management is a gap.

### `secure-sdlc`
DevSecOps and security integration in CI/CD pipelines.

- **What it does:** Embeds security gates — SAST, dependency scanning, secret detection, and policy checks — directly into the CI/CD pipeline so vulnerabilities are caught before merge.
- **When to use:** Use when establishing or maturing a DevSecOps practice, adding automated security checks to an existing pipeline, or shifting security left in the development lifecycle.

---

## DevOps

*25 skills.*

### `docker-expert`
Docker containerization and multi-stage builds.

- **What it does:** Designs and optimises Dockerfiles, multi-stage build pipelines, compose stacks, and image layer caching strategies.
- **When to use:** Reach for it when containerising an application, reducing image size, or debugging build and runtime container issues.

### `kubernetes-deployment`
Kubernetes manifests, Helm charts, and operators.

- **What it does:** Authors production-grade Kubernetes YAML, Helm charts, custom resource definitions, and operator patterns for workload management.
- **When to use:** Use when deploying, scaling, or managing workloads on a Kubernetes cluster, whether raw manifests or packaged charts.

### `ci-cd-pipeline`
CI/CD automation with GitHub Actions and Jenkins.

- **What it does:** Builds end-to-end continuous integration and delivery pipelines including test, build, security scan, and deploy stages.
- **When to use:** Reach for it when setting up or refactoring automated build, test, or deployment workflows across any CI platform.

### `infrastructure-as-code`
Terraform and Pulumi infrastructure automation.

- **What it does:** Provisions and manages cloud and on-premise infrastructure declaratively using Terraform HCL or Pulumi programs with state management.
- **When to use:** Use when standing up, modifying, or destroying infrastructure reproducibly through code rather than manual console actions.

### `aws-expert`
AWS services including EC2, S3, Lambda, RDS, and IAM.

- **What it does:** Architects, configures, and optimises AWS services covering compute, storage, serverless, databases, and identity management.
- **When to use:** Reach for it when designing or troubleshooting any AWS workload, service integration, or IAM permission model.

### `gcp-expert`
GCP services including GKE, Cloud Run, and BigQuery.

- **What it does:** Designs and deploys workloads on Google Cloud covering managed Kubernetes, serverless containers, and large-scale analytics.
- **When to use:** Use when building or migrating applications onto Google Cloud Platform or optimising existing GCP service configurations.

### `azure-expert`
Azure services including AKS, Functions, and Cosmos DB.

- **What it does:** Provisions and manages Azure infrastructure spanning managed Kubernetes, serverless functions, and globally distributed databases.
- **When to use:** Reach for it when architecting or troubleshooting workloads on Microsoft Azure across compute, serverless, or data tiers.

### `linux-administration`
Linux administration, bash scripting, and systemd.

- **What it does:** Manages Linux systems including user and process administration, shell scripting, service unit authoring, and kernel parameter tuning.
- **When to use:** Use when configuring servers, automating operational tasks, diagnosing system issues, or writing production shell scripts.

### `networking-fundamentals`
TCP/IP, DNS, load balancing, and CDN.

- **What it does:** Designs and debugs network topologies, DNS configurations, layer-4/7 load balancer rules, and CDN caching policies.
- **When to use:** Reach for it when troubleshooting connectivity issues, designing network architecture, or configuring traffic routing and distribution.

### `monitoring-observability`
Prometheus, Grafana, metrics collection, and alerting.

- **What it does:** Instruments applications and infrastructure with metrics, builds Grafana dashboards, and defines alerting rules and on-call workflows.
- **When to use:** Use when adding observability to a system, consolidating metrics pipelines, or building alerting for SLO breaches.

### `logging-aggregation`
ELK stack, Loki, and structured logging patterns.

- **What it does:** Designs log collection, parsing, and aggregation pipelines using Elasticsearch/Logstash/Kibana or Grafana Loki with structured log schemas.
- **When to use:** Reach for it when centralising logs from distributed services, building search and retention policies, or debugging log ingestion issues.

### `service-mesh`
Istio and Linkerd service mesh patterns.

- **What it does:** Configures service mesh control planes, mutual TLS, traffic shaping, circuit breaking, and observability sidecars across microservices.
- **When to use:** Use when enforcing zero-trust networking, managing east-west traffic policies, or adding mesh-level telemetry to a microservice fleet.

### `gitops`
GitOps workflows with ArgoCD and Flux.

- **What it does:** Implements GitOps delivery models where a Git repository is the single source of truth, reconciled to clusters via ArgoCD or Flux controllers.
- **When to use:** Reach for it when establishing declarative, auditable deployment pipelines driven by pull requests rather than imperative kubectl commands.

### `helm-charts`
Helm chart development and templating.

- **What it does:** Authors, lints, and versions Helm charts including values hierarchies, named templates, hooks, and chart repository publishing.
- **When to use:** Use when packaging Kubernetes applications for repeatable deployment, multi-environment configuration, or distribution via a Helm repo.

### `container-orchestration`
Container orchestration patterns and best practices.

- **What it does:** Applies scheduling, placement, health checking, rolling update, and self-healing patterns across container orchestration platforms.
- **When to use:** Reach for it when designing workload topology, resource quota strategies, or upgrade and rollback procedures for containerised services.

### `auto-scaling`
HPA, VPA, and cluster autoscaling configuration.

- **What it does:** Configures horizontal and vertical pod autoscalers, cluster autoscaler, and KEDA event-driven scaling rules to match load dynamically.
- **When to use:** Use when a service needs to scale automatically under variable load or when over-provisioned clusters need right-sizing.

### `disaster-recovery`
DR planning, backup strategies, and failover design.

- **What it does:** Designs recovery time and recovery point objectives, automated backup schedules, cross-region replication, and failover runbooks.
- **When to use:** Reach for it when defining business continuity requirements, auditing backup coverage, or engineering automated failover procedures.

### `blue-green-deployment`
Blue-green and canary deployment strategies.

- **What it does:** Implements traffic-split deployment patterns that enable zero-downtime releases, progressive rollouts, and instant rollback capabilities.
- **When to use:** Use when reducing release risk by incrementally shifting traffic to a new version before committing a full cutover.

### `configuration-management`
Ansible and Puppet configuration automation.

- **What it does:** Writes idempotent playbooks and manifests to enforce desired state across server fleets, covering packages, files, services, and users.
- **When to use:** Reach for it when managing server configuration at scale, enforcing compliance baselines, or automating repetitive provisioning tasks.

### `cloud-native`
12-factor app principles and cloud-native patterns.

- **What it does:** Applies cloud-native design principles including stateless services, externalised config, disposability, and backing-service abstractions.
- **When to use:** Use when refactoring a monolith for cloud deployment or evaluating whether an architecture adheres to cloud-native best practices.

### `cost-optimization`
FinOps, cloud cost optimisation, and spot instance strategies.

- **What it does:** Analyses cloud spend, identifies waste, right-sizes resources, and designs spot or preemptible instance strategies to reduce infrastructure cost.
- **When to use:** Reach for it when cloud bills are growing unexpectedly, before a major workload launch, or when establishing FinOps governance practices.

### `site-reliability`
SRE practices, SLA/SLO definition, and error budgets.

- **What it does:** Defines service level objectives, error budget policies, toil-reduction initiatives, and incident review processes aligned to SRE principles.
- **When to use:** Use when formalising reliability targets, building on-call culture, or applying SRE methodology to improve system dependability.

### `load-testing`
Load testing with k6, Locust, and JMeter.

- **What it does:** Designs and executes load, stress, and soak test scenarios to identify performance bottlenecks and validate capacity under peak traffic.
- **When to use:** Reach for it before a major launch, after a performance regression, or when establishing baseline throughput and latency benchmarks.

### `secrets-infrastructure`
HashiCorp Vault and external secrets management.

- **What it does:** Deploys and configures Vault for dynamic secrets, PKI, and encryption-as-a-service, plus External Secrets Operator for Kubernetes integration.
- **When to use:** Use when replacing hardcoded credentials, implementing secrets rotation, or syncing secrets from a centralised store into workloads.

### `container-registry`
Container registry management and image lifecycle.

- **What it does:** Manages container image storage, tagging conventions, vulnerability scanning, retention policies, and registry mirroring or proxying.
- **When to use:** Reach for it when setting up or hardening a container registry, enforcing image provenance, or automating image promotion workflows.

---

## Frontend

*20 skills.*

### `react-patterns`
Modern React hooks, context, and performance patterns.

- **What it does:** Implements idiomatic React using hooks, context API, memoisation, and concurrent features to build performant component trees.
- **When to use:** Reach for this when architecting React component hierarchies, optimising re-renders, or applying hook-based patterns like useReducer or custom hooks.

### `typescript-expert`
TypeScript generics, utility types, and strict-mode configuration.

- **What it does:** Applies advanced TypeScript features — generics, conditional types, mapped types, template literals, and strict compiler settings — to produce fully type-safe codebases.
- **When to use:** Use when adding strict typing to a project, designing reusable generic utilities, or resolving complex TypeScript compiler errors.

### `nextjs-expert`
Next.js App Router, SSR, and SSG patterns.

- **What it does:** Builds Next.js applications using the App Router, server components, streaming, ISR, and deployment-optimised data-fetching strategies.
- **When to use:** Reach for this when scaffolding or extending a Next.js project that requires server-side rendering, static generation, or edge-runtime patterns.

### `vue-expert`
Vue 3 Composition API, Pinia, and Nuxt integration.

- **What it does:** Develops Vue 3 applications using the Composition API, script setup syntax, Pinia state management, and Nuxt for full-stack or SSR deployments.
- **When to use:** Use when building or refactoring Vue 3 applications, migrating from Options API, or wiring up Pinia stores and Nuxt server routes.

### `angular-expert`
Angular, RxJS reactive streams, and NgRx state management.

- **What it does:** Constructs Angular applications with typed reactive forms, RxJS observable pipelines, NgRx store/effects, and Angular CLI best practices.
- **When to use:** Reach for this when working in an Angular codebase that requires reactive data flow, complex state orchestration, or enterprise-scale module architecture.

### `css-mastery`
CSS Grid, Flexbox, Tailwind, and animation techniques.

- **What it does:** Produces precise, maintainable layouts and visual effects using CSS Grid, Flexbox, custom properties, Tailwind utility classes, and keyframe animations.
- **When to use:** Use when designing complex layouts, implementing a design-token system, integrating Tailwind, or crafting performant CSS transitions and animations.

### `accessibility-expert`
WCAG compliance, ARIA semantics, and screen-reader support.

- **What it does:** Audits and remediates UI components to meet WCAG 2.1/2.2 success criteria, applying correct ARIA roles, keyboard navigation, and focus management.
- **When to use:** Reach for this when an interface must pass an accessibility audit, integrate assistive technology, or comply with legal accessibility requirements.

### `responsive-design`
Mobile-first responsive design across breakpoints.

- **What it does:** Implements fluid, breakpoint-driven layouts using mobile-first methodology, relative units, container queries, and responsive image strategies.
- **When to use:** Use when a UI must adapt gracefully from small-screen to desktop, or when retrofitting an existing layout with responsive breakpoints.

### `performance-frontend`
Core Web Vitals optimisation, lazy loading, and asset delivery.

- **What it does:** Identifies and resolves frontend performance bottlenecks by improving LCP, CLS, and INP scores through code splitting, lazy loading, caching, and resource hints.
- **When to use:** Reach for this when Core Web Vitals scores are poor, Time to Interactive is high, or a Lighthouse audit flags critical performance regressions.

### `state-management`
Redux, Zustand, and Jotai state architecture patterns.

- **What it does:** Designs and implements client-side state solutions using Redux Toolkit, Zustand stores, or Jotai atoms, with clear boundaries between local, shared, and server state.
- **When to use:** Use when an application's state complexity outgrows component-local useState, or when normalising, persisting, or synchronising state across disparate components.

### `testing-frontend`
Jest, Testing Library, and Cypress end-to-end testing.

- **What it does:** Writes unit, integration, and end-to-end tests using Jest, React Testing Library, and Cypress, covering component behaviour, accessibility queries, and full user journeys.
- **When to use:** Reach for this when adding test coverage to a frontend codebase, setting up a testing pipeline, or writing regression tests for critical user flows.

### `component-design`
Design systems, Storybook, and atomic design methodology.

- **What it does:** Builds scalable component libraries using atomic design principles, Storybook for isolated development and documentation, and design-token-driven theming.
- **When to use:** Use when establishing a shared component library, documenting UI components for a design system, or enforcing visual consistency across a product.

### `animation-expert`
Framer Motion, GSAP, and CSS animation implementation.

- **What it does:** Creates production-grade UI animations and transitions using Framer Motion declarative APIs, GSAP timelines, and performant CSS keyframe sequences.
- **When to use:** Reach for this when a design calls for complex motion choreography, scroll-driven animations, or physics-based interaction feedback.

### `form-handling`
React Hook Form, Formik, and schema-based validation.

- **What it does:** Implements controlled and uncontrolled form solutions with React Hook Form or Formik, wired to Zod or Yup schemas for client-side and server-side validation.
- **When to use:** Use when building forms that require complex validation logic, dynamic field arrays, multi-step flows, or accessible error messaging.

### `data-fetching`
TanStack Query and SWR for server-state data fetching.

- **What it does:** Manages remote data lifecycle — fetching, caching, background revalidation, optimistic updates, and pagination — using TanStack Query or SWR.
- **When to use:** Reach for this when decoupling server state from UI state, replacing manual useEffect fetch patterns, or implementing infinite scroll and mutation flows.

### `graphql-frontend`
Apollo Client, urql, and GraphQL query patterns.

- **What it does:** Integrates a GraphQL API into a frontend using Apollo Client or urql, covering queries, mutations, subscriptions, cache normalisation, and code generation.
- **When to use:** Use when a project consumes a GraphQL API and requires typed operations, reactive cache updates, or optimised query batching on the client.

### `pwa-expert`
Progressive Web App architecture, service workers, and offline-first design.

- **What it does:** Converts or builds web applications as installable PWAs with service worker caching strategies, Web App Manifests, background sync, and push notifications.
- **When to use:** Reach for this when an application must work offline, be installable on mobile home screens, or achieve a high Lighthouse PWA audit score.

### `bundler-expert`
Vite, Webpack, and esbuild configuration and optimisation.

- **What it does:** Configures and tunes JavaScript bundlers — Vite, Webpack 5, or esbuild — for optimal build performance, code splitting, tree shaking, and asset hashing.
- **When to use:** Use when a build pipeline is slow, bundle sizes are bloated, or a project needs a bundler migration or custom plugin integration.

### `monorepo-frontend`
Turborepo and Nx monorepo toolchain management.

- **What it does:** Structures multi-package frontend repositories using Turborepo or Nx, configuring task pipelines, remote caching, shared libraries, and affected-build strategies.
- **When to use:** Reach for this when managing multiple frontend apps or shared packages in a single repository that requires coordinated builds and dependency graph optimisation.

### `internationalization`
i18n, localisation, and RTL layout support.

- **What it does:** Implements multi-language support using i18next or similar libraries, handling translation loading, pluralisation, date/number formatting, and right-to-left layout mirroring.
- **When to use:** Use when a product must support multiple locales, right-to-left languages, or region-specific number and date formatting requirements.

---

## Backend

*23 skills.*

### `api-design`
RESTful API design, OpenAPI spec, and GraphQL schema authoring.

- **What it does:** Designs and documents REST or GraphQL APIs including endpoint contracts, request/response schemas, authentication flows, and OpenAPI/Swagger specifications.
- **When to use:** Reach for this when starting a new API surface, formalising an existing one, or when a GraphQL schema needs to be defined or reviewed.

### `database-design`
Database schema design, migration management, and ORM configuration.

- **What it does:** Models relational and document schemas, authors migration scripts, and configures ORM layers to align application code with the underlying data model.
- **When to use:** Reach for this when designing a new data model, adding migrations to an existing schema, or wiring up an ORM to a database.

### `nodejs-expert`
Node.js runtime, Express and Fastify frameworks, and async/await patterns.

- **What it does:** Builds performant Node.js services using Express or Fastify, applying idiomatic async patterns, middleware design, and error-handling conventions.
- **When to use:** Reach for this when building or debugging a Node.js backend, optimising async throughput, or structuring a Fastify/Express application.

### `python-patterns`
Python backend development with FastAPI, Django, and async/await.

- **What it does:** Constructs Python web services and APIs using FastAPI or Django, applying async patterns, dependency injection, and Pythonic project structure.
- **When to use:** Reach for this when building a Python API or web service, migrating to async Python, or scaffolding a FastAPI/Django project.

### `golang-expert`
Go concurrency patterns, Gin framework, and goroutine management.

- **What it does:** Implements high-throughput Go services using goroutines, channels, and the Gin framework, with correct concurrency primitives and context propagation.
- **When to use:** Reach for this when writing or reviewing Go services, optimising concurrent workloads, or debugging goroutine lifecycle issues.

### `rust-expert`
Rust ownership model, Actix-web framework, and async Tokio runtime.

- **What it does:** Builds memory-safe, high-performance Rust services with Actix-web, leveraging the ownership system and Tokio async runtime for safe concurrency.
- **When to use:** Reach for this when implementing a performance-critical Rust service, debugging borrow-checker issues, or designing async Tokio pipelines.

### `java-spring`
Spring Boot application development and dependency injection patterns.

- **What it does:** Scaffolds and maintains Spring Boot applications, configuring beans, dependency injection, Spring Security, and data access layers.
- **When to use:** Reach for this when building or extending a Spring Boot service, configuring the application context, or troubleshooting DI and bean lifecycle issues.

### `microservices-architecture`
Microservices decomposition patterns, inter-service communication, and service mesh configuration.

- **What it does:** Designs service boundaries, defines communication contracts (REST, gRPC, events), and configures service mesh tooling for observability and traffic management.
- **When to use:** Reach for this when decomposing a monolith, designing a new distributed system, or evaluating service mesh and sidecar patterns.

### `event-driven`
Event-driven architecture with Kafka, RabbitMQ, and event sourcing patterns.

- **What it does:** Designs and implements event-driven pipelines using Kafka or RabbitMQ, applying event sourcing, CQRS, and at-least-once delivery guarantees.
- **When to use:** Reach for this when decoupling services via a message broker, implementing event sourcing, or debugging consumer lag and ordering issues.

### `caching-strategies`
Caching layer design with Redis, cache invalidation strategies, and read/write patterns.

- **What it does:** Designs caching architectures — cache-aside, write-through, write-behind — and implements invalidation logic to maintain consistency between cache and source of truth.
- **When to use:** Reach for this when adding a cache to reduce latency or database load, or when diagnosing stale-data and cache stampede problems.

### `postgresql-expert`
PostgreSQL query optimisation, index design, and JSONB usage.

- **What it does:** Analyses and tunes PostgreSQL schemas and queries, designs appropriate indexes (B-tree, GIN, partial), and leverages JSONB for semi-structured data storage.
- **When to use:** Reach for this when a PostgreSQL query is slow, an index strategy needs review, or JSONB column design is required.

### `mongodb-expert`
MongoDB aggregation pipelines, index strategies, and sharding configuration.

- **What it does:** Designs MongoDB schemas for document-oriented access patterns, builds aggregation pipelines, and configures sharding and replica sets for scale.
- **When to use:** Reach for this when modelling data in MongoDB, optimising aggregation performance, or planning a sharded cluster topology.

### `redis-expert`
Redis data structures, pub/sub messaging, and Lua scripting.

- **What it does:** Applies the full Redis data-structure toolkit — sorted sets, streams, bitmaps, HyperLogLog — and implements pub/sub patterns and atomic Lua scripts for complex operations.
- **When to use:** Reach for this when Redis usage needs to go beyond simple key-value caching, or when pub/sub, streams, or atomic scripting are required.

### `elasticsearch-expert`
Elasticsearch index mapping, query DSL, and custom analyser configuration.

- **What it does:** Designs index mappings, authors complex Query DSL searches (bool, nested, aggregations), and configures text analysers for relevance-tuned full-text search.
- **When to use:** Reach for this when building or optimising a search feature, troubleshooting mapping conflicts, or tuning relevance scoring in Elasticsearch.

### `grpc-expert`
gRPC service design, Protocol Buffer schemas, and streaming RPC patterns.

- **What it does:** Defines Protobuf service contracts, generates stubs, and implements unary and streaming gRPC endpoints with interceptors and deadline propagation.
- **When to use:** Reach for this when designing low-latency inter-service communication, authoring .proto files, or debugging gRPC streaming and metadata issues.

### `websocket-expert`
WebSocket protocol, Socket.io, and real-time application architecture.

- **What it does:** Implements bidirectional real-time communication channels using native WebSockets or Socket.io, including room management, reconnection logic, and backpressure handling.
- **When to use:** Reach for this when building a real-time feature — live updates, chat, collaborative editing — or troubleshooting WebSocket connection stability.

### `serverless-architecture`
AWS Lambda function design, serverless patterns, and cold-start mitigation.

- **What it does:** Architects serverless workloads on AWS Lambda, applying event-source mappings, cold-start optimisation, and infrastructure-as-code patterns for deployment.
- **When to use:** Reach for this when designing or migrating to a serverless compute model, or when Lambda performance and cost characteristics need tuning.

### `api-versioning`
API versioning strategies and graceful deprecation workflows.

- **What it does:** Implements URI, header, or content-negotiation versioning schemes and establishes deprecation timelines, sunset headers, and migration guides for consumers.
- **When to use:** Reach for this when introducing a breaking API change, planning a versioning strategy for a public API, or managing an active deprecation cycle.

### `rate-limiting`
Rate limiting, request throttling, and quota enforcement patterns.

- **What it does:** Implements token-bucket, leaky-bucket, and fixed-window rate limiters at the API gateway or application layer, with per-tenant quota tracking and graceful 429 responses.
- **When to use:** Reach for this when an API needs abuse protection, fair-use enforcement, or tiered quota management for different client tiers.

### `background-jobs`
Background job queues with Bull, Celery, and worker process patterns.

- **What it does:** Designs and implements asynchronous job processing pipelines using Bull (Node.js) or Celery (Python), including retry logic, dead-letter queues, and worker scaling.
- **When to use:** Reach for this when offloading long-running tasks from the request cycle, configuring job queues, or debugging worker concurrency and failure handling.

### `file-upload`
File upload handling, S3 integration, and presigned URL workflows.

- **What it does:** Implements server-side file ingestion and client-side direct-upload flows using S3 presigned URLs, including multipart upload, virus scanning hooks, and storage lifecycle policies.
- **When to use:** Reach for this when adding file upload functionality, migrating uploads to object storage, or securing direct-to-S3 upload flows.

### `pagination`
Cursor-based and keyset pagination patterns for large dataset APIs.

- **What it does:** Implements stable, performant pagination using opaque cursors or keyset (seek) methods, avoiding the offset-pagination performance cliff on large tables.
- **When to use:** Reach for this when an API endpoint returns large result sets, offset pagination is causing slow queries, or a consistent cursor-based feed is required.

### `soft-delete`
Soft delete implementation, audit trails, and record versioning patterns.

- **What it does:** Adds soft-delete flags, deleted-at timestamps, and optional full audit trails or row-versioning to data models, with query scoping to exclude deleted records by default.
- **When to use:** Reach for this when data must be recoverable after deletion, a full audit trail is required by compliance, or record versioning needs to be retrofitted to an existing schema.

---

## Quality

*20 skills.*

### `test-driven-development`
TDD red-green-refactor cycle.

- **What it does:** Guides writing failing tests first, then minimal passing code, then refactoring to produce well-tested, design-driven software.
- **When to use:** Reach for this when starting a new feature or module and you want tests to drive the implementation design from the outset.

### `code-review`
Code review best practices and structured feedback.

- **What it does:** Applies established review heuristics to evaluate correctness, readability, security, and maintainability, then produces actionable, prioritised feedback.
- **When to use:** Use when reviewing a pull request, diff, or patch and you need structured, evidence-based critique rather than ad-hoc comments.

### `debugging-expert`
Debugging strategies, profiling, and tracing.

- **What it does:** Applies systematic fault-isolation techniques — hypothesis-driven debugging, profiler analysis, and distributed tracing — to locate and explain defects.
- **When to use:** Reach for this when a bug is non-obvious or intermittent and you need a disciplined, tool-assisted investigation rather than guesswork.

### `refactoring-guide`
Refactoring patterns and clean code principles.

- **What it does:** Identifies code smells, selects the appropriate refactoring pattern (extract method, replace conditional with polymorphism, etc.), and applies changes without altering external behaviour.
- **When to use:** Use when existing code is difficult to read, extend, or test and you want a safe, incremental improvement plan.

### `performance-optimization`
Performance profiling and optimization techniques.

- **What it does:** Profiles runtime and memory behaviour, pinpoints hot paths and bottlenecks, and applies targeted optimizations backed by before/after benchmarks.
- **When to use:** Reach for this when latency, throughput, or resource consumption falls outside acceptable thresholds and you need data-driven fixes rather than intuition.

### `unit-testing`
Unit testing, mocking, and fixtures.

- **What it does:** Designs isolated, fast unit tests with appropriate mocks, stubs, and fixtures to verify individual functions and classes in isolation.
- **When to use:** Use when writing or improving tests for a single module or function where external dependencies must be controlled.

### `integration-testing`
Integration testing and API testing.

- **What it does:** Constructs tests that exercise multiple components or services together — including real HTTP calls, database interactions, and message queues — to verify correct integration.
- **When to use:** Reach for this when you need confidence that independently tested components behave correctly when wired together.

### `e2e-testing`
End-to-end testing with Playwright and Cypress.

- **What it does:** Authors and maintains browser-driven E2E test suites using Playwright or Cypress, covering full user journeys from UI interaction to backend response.
- **When to use:** Use when you need to validate complete user flows in a real browser environment, especially before major releases or after significant UI changes.

### `test-coverage`
Code coverage measurement and threshold enforcement.

- **What it does:** Instruments codebases to measure line, branch, and statement coverage, interprets reports, and enforces minimum thresholds in CI pipelines.
- **When to use:** Reach for this when you need to quantify test completeness, identify untested paths, or gate deployments on a coverage floor.

### `mutation-testing`
Mutation testing for test suite quality.

- **What it does:** Introduces systematic code mutations and checks whether the existing test suite detects them, surfacing weak assertions and gaps in test logic.
- **When to use:** Use when coverage metrics look healthy but you suspect tests are not actually verifying the right behaviour.

### `property-based-testing`
Property-based testing and fuzzing.

- **What it does:** Generates large volumes of randomised, constraint-driven inputs to find edge cases that example-based tests would not exercise.
- **When to use:** Reach for this when a function's correctness must hold across a wide input space and you want automated discovery of counter-examples.

### `visual-regression`
Visual regression testing with Percy and Chromatic.

- **What it does:** Captures baseline UI screenshots and diffs them against subsequent builds using Percy or Chromatic to catch unintended visual changes.
- **When to use:** Use when UI components must remain pixel-consistent across releases and you need automated visual sign-off in the CI pipeline.

### `api-contract-testing`
Pact contract testing and consumer-driven contracts.

- **What it does:** Defines and verifies API contracts between consumers and providers using Pact, ensuring both sides honour agreed schemas without requiring live integration environments.
- **When to use:** Reach for this when multiple teams or services evolve independently and you need early detection of breaking API changes.

### `load-testing-expert`
Load testing with k6 and Gatling.

- **What it does:** Designs and executes realistic load and stress test scenarios using k6 or Gatling, measuring throughput, latency percentiles, and failure modes under pressure.
- **When to use:** Use before a major launch, infrastructure change, or when you need to establish or validate SLA thresholds under peak traffic.

### `code-quality-tools`
Static analysis with ESLint, Prettier, and SonarQube.

- **What it does:** Configures and integrates linters, formatters, and static analysis platforms to enforce consistent style and surface quality or security issues automatically.
- **When to use:** Reach for this when setting up a new project's quality gates or auditing an existing codebase's toolchain configuration.

### `documentation`
Technical documentation and JSDoc authoring.

- **What it does:** Produces clear, accurate technical documentation — inline JSDoc, API references, architecture decision records, and developer guides — matched to the intended audience.
- **When to use:** Use when code, APIs, or architectural decisions need to be documented for maintainability, onboarding, or public consumption.

### `error-handling`
Error handling and recovery patterns.

- **What it does:** Applies structured error-handling strategies — typed errors, circuit breakers, retry with back-off, graceful degradation — to make systems resilient and diagnosable.
- **When to use:** Reach for this when designing or hardening failure paths in an application where unhandled exceptions or silent failures are a risk.

### `logging-best-practices`
Structured logging and log level strategy.

- **What it does:** Implements structured, machine-parseable logging with appropriate severity levels, contextual fields, and correlation IDs suitable for log aggregation and alerting.
- **When to use:** Use when setting up observability for a new service or auditing noisy, unstructured logs that make debugging in production difficult.

### `code-maintainability`
SOLID principles and long-term maintainability.

- **What it does:** Evaluates code against SOLID, DRY, and related principles, then proposes concrete structural changes to reduce coupling and improve changeability.
- **When to use:** Reach for this when a codebase is becoming expensive to extend and you need a principled diagnosis before committing to a larger refactor.

### `technical-debt`
Technical debt management and modernization planning.

- **What it does:** Audits accumulated technical debt, quantifies its carrying cost, and produces a prioritised remediation roadmap that balances delivery velocity against long-term health.
- **When to use:** Use when a codebase has grown hard to change, onboard into, or operate, and the team needs a structured plan to retire the debt incrementally.

---

## Data & AI

*21 skills.*

### `data-analysis`
Statistical analysis and data insights.

- **What it does:** Applies descriptive and inferential statistics to surface patterns, distributions, and actionable insights from raw datasets.
- **When to use:** Reach for it when you need to explore, summarise, or draw conclusions from a dataset before or after modelling.

### `financial-analysis`
DCF, valuation, and financial modelling.

- **What it does:** Builds discounted cash-flow models, comparable-company analyses, and structured financial projections from first principles.
- **When to use:** Use when evaluating an investment, pricing a deal, or producing a rigorous financial model with explicit assumptions.

### `machine-learning`
ML pipelines, scikit-learn, and XGBoost.

- **What it does:** Designs and trains supervised and unsupervised machine-learning pipelines using scikit-learn, XGBoost, and related libraries.
- **When to use:** Reach for it when building a classification, regression, or clustering model on structured tabular data.

### `deep-learning`
PyTorch and TensorFlow deep learning.

- **What it does:** Architects, trains, and fine-tunes deep neural networks using PyTorch or TensorFlow for complex prediction tasks.
- **When to use:** Use when the problem requires neural network depth — image recognition, sequence modelling, or tasks beyond classical ML.

### `nlp-expert`
NLP, transformers, and text processing.

- **What it does:** Processes, tokenises, and models natural language using transformer architectures and standard NLP pipelines.
- **When to use:** Reach for it when the input is unstructured text and the goal involves classification, extraction, generation, or semantic understanding.

### `computer-vision`
Computer vision, OpenCV, and YOLO.

- **What it does:** Detects, segments, and classifies objects in images and video using OpenCV, YOLO, and convolutional architectures.
- **When to use:** Use when the task involves interpreting image or video data — object detection, OCR, or visual quality inspection.

### `data-engineering`
ETL pipelines, Airflow, and Spark.

- **What it does:** Designs and orchestrates batch and streaming data pipelines using Apache Airflow, Spark, and modern ETL patterns.
- **When to use:** Reach for it when raw data must be ingested, transformed, and delivered reliably at scale.

### `data-visualization`
D3.js, Plotly, and data dashboards.

- **What it does:** Produces interactive and static charts, dashboards, and visual narratives using D3.js, Plotly, and dashboard frameworks.
- **When to use:** Use when findings need to be communicated visually — exploratory charts, executive dashboards, or embedded analytics.

### `pandas-expert`
Pandas and NumPy data manipulation.

- **What it does:** Performs high-performance data wrangling, reshaping, and computation using Pandas DataFrames and NumPy arrays.
- **When to use:** Reach for it whenever structured data needs cleaning, merging, aggregating, or transforming in Python.

### `sql-analytics`
Advanced SQL, window functions, and CTEs.

- **What it does:** Writes complex analytical queries using window functions, CTEs, and set operations to answer business questions directly in SQL.
- **When to use:** Use when the analysis lives in a relational database and requires more than simple SELECT statements.

### `bigquery-expert`
BigQuery, partitioning, and optimisation.

- **What it does:** Designs cost-efficient BigQuery schemas, partitioned tables, and optimised queries for petabyte-scale analytics on Google Cloud.
- **When to use:** Reach for it when working in a BigQuery environment and query cost or performance needs deliberate tuning.

### `snowflake-expert`
Snowflake data warehousing.

- **What it does:** Models, loads, and queries data in Snowflake, leveraging virtual warehouses, clustering keys, and Snowpark where appropriate.
- **When to use:** Use when the data warehouse is Snowflake and the task involves schema design, query optimisation, or data sharing.

### `dbt-expert`
dbt models, tests, and documentation.

- **What it does:** Builds modular dbt transformation layers with tested, documented, version-controlled SQL models following best-practice project structure.
- **When to use:** Reach for it when defining or refactoring the analytics engineering layer in a dbt project.

### `time-series`
Time series forecasting and Prophet.

- **What it does:** Builds and evaluates time series forecasting models using Prophet, ARIMA, and related methods with appropriate seasonality handling.
- **When to use:** Use when the target variable is indexed by time and the goal is to project future values or detect anomalies.

### `recommendation-systems`
Recommendation engines and collaborative filtering.

- **What it does:** Implements collaborative filtering, content-based, and hybrid recommendation algorithms to personalise item or content ranking.
- **When to use:** Reach for it when building a system that suggests products, content, or connections based on user behaviour.

### `ab-testing`
A/B testing and experiment design.

- **What it does:** Designs statistically valid experiments, calculates sample sizes, and analyses results including multiple-comparison corrections.
- **When to use:** Use when evaluating the causal impact of a product change or intervention through controlled experimentation.

### `feature-engineering`
Feature engineering and selection.

- **What it does:** Creates, transforms, and selects predictive features from raw data to maximise model signal while controlling dimensionality.
- **When to use:** Reach for it when model performance is limited by feature quality or when domain knowledge needs encoding into ML inputs.

### `model-deployment`
MLOps, model serving, and inference.

- **What it does:** Packages trained models into production-ready serving infrastructure with monitoring, versioning, and CI/CD integration.
- **When to use:** Use when a trained model needs to move from notebook to a live endpoint or batch inference pipeline.

### `llm-integration`
LLM APIs, LangChain, and prompting.

- **What it does:** Integrates large language models into applications via API, LangChain, or direct SDK calls with structured prompting patterns.
- **When to use:** Reach for it when building a product feature, workflow, or agent that calls an LLM as a core component.

### `rag`
RAG pipelines, vector search, and embeddings.

- **What it does:** Builds retrieval-augmented generation systems combining dense vector search with LLM generation for grounded, source-cited answers.
- **When to use:** Use when an LLM needs to answer questions over a private or dynamic knowledge base rather than relying on parametric memory.

### `sentiment-analysis`
Sentiment analysis and opinion mining.

- **What it does:** Classifies sentiment polarity and extracts opinion signals from text using fine-tuned models or zero-shot transformer inference.
- **When to use:** Reach for it when measuring customer sentiment, brand perception, or opinion trends from reviews, surveys, or social data.

---

## Business

*20 skills.*

### `market-research`
Market sizing, TAM/SAM/SOM analysis.

- **What it does:** Structures and quantifies addressable markets using TAM/SAM/SOM frameworks, pulling from industry reports, filings, and primary data to produce a defensible market sizing model.
- **When to use:** Reach for this when entering a new market, validating a business opportunity, or preparing investor materials that require a credible market size estimate.

### `competitive-intelligence`
SWOT analysis, competitive positioning.

- **What it does:** Maps the competitive landscape using SWOT, Porter's Five Forces, and positioning matrices to identify threats, white space, and sustainable differentiation.
- **When to use:** Use this when launching a product, preparing a competitive response, or needing a structured view of how a business stacks up against direct and indirect rivals.

### `go-to-market`
GTM strategy, positioning, messaging.

- **What it does:** Produces a go-to-market plan covering channel selection, ICP definition, messaging hierarchy, launch sequencing, and success metrics.
- **When to use:** Trigger this when preparing to launch a product or enter a new segment and needing a structured plan for reaching and converting target customers.

### `business-plan-template`
Business planning, strategic roadmap.

- **What it does:** Generates a structured business plan covering executive summary, market analysis, operating model, financial projections, and strategic milestones.
- **When to use:** Use this when founding a new venture, pivoting a business, or needing a formal planning document for internal alignment or external stakeholders.

### `investor-pitch`
Pitch deck, investor materials.

- **What it does:** Builds investor-grade pitch materials including narrative arc, market sizing, traction slides, business model, team, and ask — structured for VC or PE audiences.
- **When to use:** Reach for this when preparing for a fundraising round, angel outreach, or any presentation where capital allocation decisions will be made.

### `brainstorming`
Ideation frameworks, brainstorming.

- **What it does:** Facilitates structured ideation using frameworks such as SCAMPER, first-principles decomposition, and analogical reasoning to generate and screen high-quality ideas.
- **When to use:** Use this at the front end of any problem — new product concepts, solution generation, naming, or strategic pivots — where divergent thinking is needed before convergence.

### `report-generation`
Executive reports, summaries.

- **What it does:** Synthesises research, data, and analysis into structured executive reports with a clear summary, key findings, and recommended actions formatted for decision-makers.
- **When to use:** Trigger this when findings from research or analysis need to be packaged into a polished, shareable document for leadership, investors, or clients.

### `pricing-strategy`
Pricing models, monetization.

- **What it does:** Evaluates and designs pricing models — value-based, cost-plus, tiered, freemium, usage-based — with supporting analysis of price elasticity, competitive benchmarks, and revenue impact.
- **When to use:** Use this when setting initial prices, restructuring a pricing model, or testing monetisation strategies for a new product or market segment.

### `customer-research`
User research, persona development.

- **What it does:** Designs and synthesises customer research — interview frameworks, survey structures, jobs-to-be-done mapping, and persona development — to surface validated customer insights.
- **When to use:** Reach for this before building or repositioning a product, when assumptions about the customer need validation, or when preparing a persona-driven marketing strategy.

### `product-market-fit`
PMF validation, MVP testing.

- **What it does:** Structures a PMF validation process including hypothesis definition, minimum viable test design, leading indicator selection, and interpretation of retention and engagement signals.
- **When to use:** Use this when assessing whether an early product has found its market, or designing the experiments needed to iterate toward product-market fit.

### `unit-economics`
CAC, LTV, payback period.

- **What it does:** Builds a unit economics model calculating CAC, LTV, LTV:CAC ratio, gross margin contribution, and payback period with scenario sensitivity.
- **When to use:** Trigger this when evaluating business model health, preparing investor diligence materials, or stress-testing growth assumptions against cost of acquisition.

### `financial-modeling`
Financial projections, modeling.

- **What it does:** Constructs three-statement financial models, DCF valuations, and scenario analyses with clearly stated assumptions, driver trees, and sensitivity tables.
- **When to use:** Use this when building a business case, valuing an asset, preparing board financials, or stress-testing strategic decisions against financial outcomes.

### `okr-planning`
OKR frameworks, goal setting.

- **What it does:** Designs an OKR framework aligned to strategic priorities, with objective cascading from company to team level, key result definitions, and a cadence for tracking.
- **When to use:** Reach for this at the start of a planning cycle, when aligning teams around shared priorities, or when existing goals lack measurability or strategic coherence.

### `stakeholder-management`
Stakeholder alignment, comms.

- **What it does:** Maps stakeholder influence and interest, then designs a communication and engagement plan to build alignment, manage resistance, and maintain trust throughout a programme.
- **When to use:** Use this when a project or change initiative involves multiple parties with competing interests, or when securing buy-in is a prerequisite to progress.

### `risk-assessment`
Risk assessment, mitigation plans.

- **What it does:** Produces a structured risk register with likelihood and impact scoring, root cause analysis, and prioritised mitigation actions for strategic, operational, or financial risks.
- **When to use:** Trigger this before committing to a major decision, investment, or launch — or when a project requires formal risk documentation for governance or investor purposes.

### `partnership-strategy`
Partnership development.

- **What it does:** Identifies and evaluates partnership opportunities, structures deal rationale, outlines mutual value propositions, and maps negotiation levers and integration requirements.
- **When to use:** Use this when considering strategic alliances, distribution partnerships, technology integrations, or co-marketing arrangements that require a structured approach.

### `growth-hacking`
Growth loops, viral mechanics.

- **What it does:** Designs data-driven growth experiments including referral loops, viral mechanics, activation funnels, and retention levers, prioritised by expected impact and implementation cost.
- **When to use:** Reach for this when optimising top-of-funnel acquisition, improving activation rates, or building compounding growth loops into a product or distribution model.

### `content-strategy`
Content strategy, SEO, thought leadership.

- **What it does:** Develops a content strategy covering audience mapping, topic clusters, SEO keyword architecture, distribution channels, and a publishing cadence tied to business objectives.
- **When to use:** Use this when building organic acquisition, establishing category authority, or aligning content production to a defined pipeline or demand-generation goal.

### `sales-strategy`
Sales strategy, pipeline management.

- **What it does:** Designs a sales motion covering ICP prioritisation, outreach sequencing, pipeline stage definitions, conversion benchmarks, and quota and forecasting frameworks.
- **When to use:** Trigger this when building or restructuring a sales function, entering a new market segment, or diagnosing underperformance in an existing revenue pipeline.

### `legal-compliance`
Legal compliance, contracts.

- **What it does:** Reviews compliance requirements, flags legal risk areas, and structures contract frameworks covering key clauses, liability exposure, and regulatory obligations relevant to the business context.
- **When to use:** Use this when entering new markets, structuring commercial agreements, assessing regulatory exposure, or preparing for a transaction that requires legal due diligence.

---

## Atlas-native skills

*4 skills.* These are the first-class skills that ship installed with Atlas OS
and integrate directly with the knowledge vault, RAG search, and email tooling.
Unlike the capability skills above (which describe expertise an agent applies),
these are concrete, runnable `SKILL.md` automations.

### `autoresearch`
Autonomous web research that synthesises findings into a cited vault note.

- **What it does:** Runs multiple rounds of web search (overview, deep dive, recent developments), cross-references existing vault content, and writes a structured, cited wiki note — then updates the index, log, and hot cache.
- **When to use:** Trigger it when you say "research this", "look into", or "find out about" a topic and want the result captured as a permanent, searchable note.

### `save-to-vault`
Capture a conversation, decision, or finding as a structured vault note.

- **What it does:** Classifies the content (conversation / decision / finding / meeting / reference), creates structured frontmatter, writes the note, and updates the log and backlinks.
- **When to use:** Use it when you say "save this", "note this", or "save to vault" and want something from the current session kept in the knowledge base.

### `wiki-search`
Semantic (RAG) search over the knowledge vault with cited answers.

- **What it does:** Checks the index, runs semantic vector search, falls back to grep, reads the matched source notes, and synthesises an answer with citations and related-note pointers.
- **When to use:** Reach for it when you ask "what do I have on…", "search the vault", or want an answer grounded in your own notes rather than general knowledge.

### `send-email`
Send an email (HTML, plain text, attachments) via SMTP.

- **What it does:** Sends mail from the configured account over SMTP with HTML or plain-text bodies and file attachments (PDF, DOCX, XLSX), reading credentials from `SMTP_APP_PASSWORD` / `SENDER_EMAIL` in the environment.
- **When to use:** Use it whenever a task needs to email a report, document, or summary — credentials are never inlined, only read from the environment.

---

## Scheduled automations

*9 tasks.* These are the scheduled-task `SKILL.md` prompts in
[`skills/`](../skills) — Claude Cowork skills that run on a cadence. Each is fully
templated with `{{PLACEHOLDER}}` tokens; install one by copying its folder into
your scheduled-tasks directory and replacing the tokens. Full cadences,
placeholder tokens, and safety notes are in
[**SCHEDULED-TASKS.md**](SCHEDULED-TASKS.md).

| Skill | Suggested cadence | What it does |
|---|---|---|
| `nightly-obsidian-index` | Nightly (~02:00) | Index changed notes, sync the wiki, append the hot cache, commit the vault, write a morning briefing |
| `nightly-rag-incremental` | Nightly (after the index) | Embed only notes changed since the last run |
| `morning-session-capture` | Morning (~09:00) | Capture overnight/early-morning Cowork transcripts to the vault (`--since 12h`) |
| `afternoon-session-capture` | Late afternoon (~17:00–18:00) | Capture the day's Cowork transcripts to the vault (`--since 12h`) |
| `daily-session-capture` | Nightly (~23:30) | Single once-a-day alternative — save the day's Cowork transcripts (`--since 24h`) |
| `daily-job-tracker-update` | Weekday mornings | Scan email for application updates; update a tracker spreadsheet |
| `afternoon-job-tracker-update` | Weekday ~14:00 | Catch afternoon emails; update the tracker |
| `atlas-daily-report-email` | Daily (~09:30) | Email a status report (activity, system health, action items) |
| `daily-trading-report` | Daily (~13:00) | Run analyst agents on a watchlist; email a research report |
| `friday-it-newsletter` | Fridays AM | Compile and email a weekly news digest; save it to the vault |
| `weekly-system-health-check` | Weekly | Probe every subsystem; email a health report; auto-fix safe issues |
| `weekly-rag-full-reembed` | Weekly (Sun early AM) | Re-embed the entire vault from scratch |

> The job-tracker, trading, and newsletter tasks are optional and only useful if
> those workflows apply to you. Start with the index + RAG + health tasks and add
> others as needed.

---

## Adding your own

These skills are a starting menu, not a fixed set. To add a capability or a new
automation, drop a `skills/<slug>/SKILL.md` with `name` + `description`
frontmatter and a numbered-step body, then run `atlas skills --sync` to
regenerate the in-vault `Skills Catalog.md` so agents can discover it. See
[**SKILLS-FRAMEWORK.md**](SKILLS-FRAMEWORK.md) for the anatomy, lifecycle, and a
copy-paste template, and the
[**skill-creator**](SKILLS-FRAMEWORK.md#creating-a-custom-skill) meta-skill for
scaffolding one.
