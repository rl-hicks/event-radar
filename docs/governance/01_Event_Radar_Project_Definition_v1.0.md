# Event Radar — Project Definition Artifact

**Version:** 1.0  
**Status:** ACCEPTED / GOVERNING  
**Accepted:** 2026-10-02  
**Artifact type:** Project Definition  
**Project owner:** Robot  
**Formation conversation:** Event Radar Project Kickstarter  
**Governing framework:** Project Artifact Architecture v2; Project Conversation Architecture & Development Operating Model v1.0

---

## 1. Authority

This artifact is the highest-level governing definition of the Event Radar project.

It defines the project’s identity, purpose, intended outcome, durable principles, scope, non-goals, assumptions, constraints, existing assets, decision authority, and downstream artifact boundaries.

Downstream artifacts may make this project more specific. They may not silently redefine it.

This artifact remains authoritative until explicitly superseded by an owner-approved revision.

---

## 2. Project identity

The Event Radar project is the effort to **productize an already-working personal weekend-research system into a small, local, paid product for external users**.

The project begins from a functioning single-user Event Radar that already performs local event collection, semantic analysis, complementary web discovery, weather-aware activity reasoning, hike integration, personalization, and weekly packet generation for its original user.

The project is therefore not:

> “Invent an event recommender from scratch.”

It is:

> **Transform a proven single-user weekend-intelligence system into an owned, multi-user product that researches a person’s weekend for them, personalizes the result, and tests whether that value is strong enough for strangers to pay for and use repeatedly.**

The existing system is a major starting asset.

Its current implementation is not automatically the public-product architecture.

---

## 3. Core project thesis

The core customer-facing thesis is:

> **Your weekend, researched for you.**

Event Radar should reduce the work required to discover, compare, and decide what is worth doing locally.

It is not primarily:

- an event calendar;
- another Eventbrite;
- a generic recommendation feed;
- a scraped local directory;
- a social network;
- or “ChatGPT but for weekends.”

AI, web search, databases, job runners, and conversational interfaces are mechanisms.

The project identity is the user outcome:

- better local discovery;
- less search work;
- personal relevance;
- better judgment about friction and payoff;
- and a usable decision set for the weekend.

---

## 4. Why the project exists

Local weekend discovery is fragmented.

A person trying to use a weekend well may need to:

- search multiple event calendars and venue pages;
- find smaller or obscure opportunities that major platforms miss;
- resolve incomplete or inconsistent listings;
- compare activities with very different formats;
- account for schedule, weather, cost, travel friction, and current intent;
- distinguish genuinely worthwhile experiences from generic local programming;
- and convert all of that into an actual decision.

That burden often produces weak default behavior despite abundant local activity.

Event Radar exists to convert that fragmented research and judgment process into a recurring service.

The intended benefit is:

> **less searching, stronger discovery, better judgment, and easier weekend decisions.**

---

## 5. Intended project outcome

The project will produce a **launch-capable local Event Radar subscription product** that:

1. serves people outside the builder’s private workflow;
2. researches local weekend opportunities deeply enough to create meaningful discovery rather than merely reproduce a calendar;
3. personalizes that research to each user;
4. produces a useful decision set rather than a rigid itinerary;
5. exists as an Event Radar-owned product with durable user and product state;
6. can operate without ChatGPT being the only product surface;
7. supports a legitimate paid relationship;
8. operates credibly on a recurring weekend cadence;
9. protects private user state;
10. communicates uncertainty and degraded states honestly;
11. and produces evidence about whether people will pay, return, and act on the product’s recommendations.

The project is both:

- a **product-construction project**; and
- a **market-validation project**.

The first meaningful commercial proof is:

> **An external user with no obligation to the builder chooses to pay for Event Radar and uses it in a real weekend decision.**

Repeat use and retention determine whether that value is durable.

---

## 6. Governing commitments

### 6.1 Local first

The proving region is **Sonoma County / the North Bay**.

The project will pursue depth and usefulness in one real geography before broad geographic expansion.

A national-first launch is outside the current project identity.

### 6.2 Personalization is fundamental

Event Radar is not a generic local feed.

A user’s interests, dislikes, schedule, cost tolerance, travel tolerance, social posture, activity preferences, recurring constraints, and current-week intent may materially change what should be surfaced.

The precise product representation belongs downstream.

The need for meaningful per-user judgment does not.

### 6.3 Research quality over recommendation volume

The product should optimize for high-signal discovery and decision value.

Recommendation count is not a success metric by itself.

The project must not become a scraped calendar with personalized prose attached.

### 6.4 User agency

Event Radar is decision support.

The user remains the decision-maker.

The project may later support outing composition, but a rigid itinerary is not the core product identity.

### 6.5 Event Radar owns the durable product

Event Radar owns the durable customer and product relationship.

External platforms may provide:

- AI;
- authentication;
- billing;
- hosting;
- delivery;
- or conversational access.

They must not be the sole place where Event Radar exists or the sole repository of its durable user/product state.

### 6.6 Facts, interpretation, and uncertainty remain distinct

The product operates on volatile local information.

The project must not treat inferred, stale, uncertain, or unverified information as permanent fact.

The implementation of provenance and verification belongs downstream.

The distinction itself is governing.

### 6.7 Validate before broadening

The project will not use feature expansion as a substitute for testing the core value proposition.

The early governing question is:

> **Does Event Radar save enough real weekend-planning effort and produce enough useful discovery that external users will pay and return?**

### 6.8 Reuse the existing system where it remains fit

The current personal Event Radar is a foundation candidate, not disposable history.

Downstream engineering should preserve, extract, adapt, or refactor validated parts where doing so remains technically sound.

The project does not require preserving implementation choices that were specific to one user.

---

## 7. Project scope

The project includes:

- converting the personal Event Radar into an externally usable product;
- establishing a public Event Radar web experience;
- supporting multiple users;
- maintaining meaningful regional weekend research;
- separating shared regional intelligence from per-user recommendation judgment;
- supporting persistent user context and temporary weekend intent;
- producing recurring personalized Weekend Packets;
- maintaining durable product state;
- supporting a legitimate paid relationship;
- providing reliable recurring delivery or notification;
- protecting private user state;
- creating truthful failure and degraded-state behavior;
- evaluating the product with external users;
- measuring evidence relevant to usefulness, repeat use, and willingness to pay;
- and productizing or extracting the existing engine as required to support those outcomes.

---

## 8. Project-level non-goals

The current project is not:

- a national event marketplace;
- an Eventbrite competitor;
- a venue-management system;
- a general local social network;
- a follower or creator platform;
- an advertising marketplace;
- a user-review network;
- a giant recommendation feed;
- a project to recreate ChatGPT;
- or a project whose success is defined by feature count.

The project does not require:

- a native mobile application;
- complex maps;
- venue dashboards;
- community features;
- national coverage;
- a custom conversational UI;
- or large-scale infrastructure.

Such capabilities may be admitted later through the proper artifact.

---

## 9. Existing starting assets

The project begins with substantial working assets:

- a public `rl-hicks/event-radar` codebase;
- a private runtime/state repository;
- a Python/uv application and CLI;
- event collection from Sonoma County Tourism and Happening Sonoma County;
- normalization and deduplication;
- source-aware price handling;
- a semantic scraped-event analysis stage;
- complementary AI web discovery;
- a final personalization/curation stage;
- Open-Meteo weather integration;
- a curated North Bay hike catalog and deterministic weather suitability;
- private user-context and preference-policy handling;
- Telegram delivery;
- GitHub Actions weekly production;
- bounded source and provider failure handling;
- audit artifacts;
- token/cost telemetry;
- and a demonstrated ability to produce useful personalized weekend packets.

These assets reduce domain and recommendation-engine risk.

They do not solve the multi-user product, persistence, auth, billing, or public UX requirements.

---

## 10. Working assumptions

The project proceeds on the following testable assumptions:

1. Weekend-planning friction is valuable enough to solve.
2. Research plus personalization is materially more useful than listings alone.
3. Local depth can differentiate the product.
4. The current personal system can contribute materially to the public product.
5. Regional research can be shared across users.
6. User-specific judgment can happen downstream from shared research.
7. Some external users will pay.
8. The weekly nature of the problem can support repeat use.
9. External AI systems can remain dependencies rather than owners of the product.
10. The current cost structure is compatible with small-scale paid validation if shared research is reused.

These assumptions are subject to evidence.

---

## 11. Major constraints and dependencies

### 11.1 Single-user starting architecture

The current system was designed for one known user.

Single-user assumptions must not become public-product assumptions by accident.

### 11.2 Dynamic local information

Events, prices, weather, availability, closures, trail access, hours, and parking conditions can change quickly.

### 11.3 Third-party sources

Local source structure and reliability can change without notice.

### 11.4 External services

The product will depend on external services for some combination of AI, hosting, auth, billing, email, and data.

### 11.5 Scope pressure

The concept naturally expands into restaurants, coffee, maps, outing chaining, real-time planning, partner profiles, and new geographies.

Those extensions must not delay proof of the core product without a governing reason.

### 11.6 Paid validation

Free usage alone does not answer the full project question.

The project must support and test a real paid relationship.

---

## 12. Candidate future directions

The following are recognized future possibilities, not current project requirements:

- ChatGPT-native Event Radar access;
- Event Radar tools/API exposed to ChatGPT;
- “Continue with ChatGPT” authentication;
- restaurant and coffee knowledge;
- broader local-place knowledge;
- geographic chaining;
- anchor-based outing construction;
- real-time planning;
- maps;
- saved favorites;
- partner/family profiles;
- additional North Bay coverage;
- additional cities;
- and native mobile applications.

These may be admitted later through the Product Definition or a future project revision.

---

## 13. Deliberately open project-level decisions

The following remain open until downstream work makes them decision-worthy:

- exact public subscription price;
- billing cadence;
- trial or preview structure;
- exact market-validation threshold;
- final public brand/domain naming;
- timing of any ChatGPT-native integration;
- ultimate geographic expansion;
- and future local-place breadth.

Repository topology, framework details, database, auth provider, deployment platform, scheduler, and model configuration are engineering decisions and are governed downstream.

---

## 14. Artifact authority

The governing chain is:

> **Project Definition**  
> ↓  
> **Product Definition**  
> ↓  
> **Product Phase Roadmap**  
> ↓  
> **Engineering Phase Map**  
> ↓  
> **Active Engineering Execution Roadmap**  
> ↓  
> **Implementation and verification**  
> ↓  
> **Phase Handoff / Closeout**  
> ↓  
> **Project Tracker**

The Product Definition owns the required destination product.

The Product Phase Roadmap owns product maturity staging.

The Engineering Phase Map owns the high-level technical path.

The active Engineering Execution Roadmap owns detailed execution for the current engineering phase.

The Project Tracker owns factual execution state and evidence.

---

## 15. Conversation operating model

Project formation is owned by the Kickstarter Conversation.

After the initial formation set is accepted:

- the Project Manager becomes the primary coordination layer;
- one Engineering Execution Conversation owns each engineering phase;
- branches solve bounded subproblems and return explicit handoffs;
- phase closeouts return to the Project Manager and Project Tracker;
- the predecessor execution conversation drafts the next Engineering Execution Roadmap from actual resulting state;
- and the Project Manager reconciles and activates the next phase.

Conversation memory is not a competing source of authority.

Accepted artifacts and verified handoffs control within their defined domains.

---

## 16. Change routing

A change to project identity, purpose, intended outcome, durable principles, or fundamental scope requires Project Definition revision.

A change to required product capability or product behavior belongs in the Product Definition.

A change to product staging belongs in the Product Phase Roadmap.

A change to high-level stack, architecture, migration direction, or engineering-phase structure belongs in the Engineering Phase Map.

A change to active implementation method belongs in the Engineering Execution Roadmap if upstream commitments remain intact.

Actual execution state belongs in the Project Tracker.

---

## 17. Fundamental change authority

Robot, as project owner, retains final authority over changes to governing project and product commitments.

The following would require explicit Project Definition reconsideration:

- converting Event Radar into a generic event marketplace;
- removing meaningful personalization;
- abandoning local-first validation for national-first launch;
- making another platform the sole home of the product;
- abandoning paid validation;
- or changing Event Radar into a materially different product category.

---

## 18. Stability test

This remains the same project if any of the following change:

- repository layout;
- technical stack;
- GitHub Actions usage;
- database;
- auth provider;
- deployment provider;
- AI model/provider;
- packet design;
- onboarding fields;
- product-version count;
- engineering-phase count;
- subscription price;
- payment provider;
- notification provider;
- or the amount of current code reused.

Those decisions belong downstream unless they change project identity.

---

## 19. Governing status

**ACCEPTED / GOVERNING — VERSION 1.0**

This artifact is implementation-authoritative for project identity and scope.

Any future revision must be explicit and supersede this version through the project’s governing process.
