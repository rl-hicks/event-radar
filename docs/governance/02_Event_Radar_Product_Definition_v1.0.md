# Event Radar — Product Definition Artifact

**Version:** 1.0  
**Status:** ACCEPTED / GOVERNING  
**Accepted:** 2026-10-02  
**Artifact type:** Product Definition  
**Upstream authority:** Event Radar — Project Definition Artifact v1.0  
**Project owner:** Robot

---

## 1. Authority

This artifact defines the required Event Radar product state.

It governs:

- who the product serves;
- the problem it solves;
- product objects;
- required product behavior;
- user/system flows;
- functional and nonfunctional requirements;
- ownership, persistence, privacy, and reliability expectations;
- interfaces and outputs;
- readiness criteria;
- and product-level non-goals.

It does not define implementation order or detailed engineering method.

---

## 2. Product definition

**Event Radar is a local subscription product that researches the coming weekend, constructs a reusable regional opportunity universe, combines that research with each user’s persistent context and current-week intent, and delivers a personalized Weekend Packet that helps the user choose worthwhile ways to spend the weekend without doing the research from scratch.**

---

## 3. Product purpose

Event Radar exists to move the user from:

> “I should do something this weekend, but I do not know what is actually worth doing.”

to:

> “I have a credible, personalized set of options and understand why each may or may not be worth my time.”

The product creates value only if it improves the user’s decision surface.

Collecting events is not enough.

Generating plausible text is not enough.

The product must combine:

1. regional research;
2. individual context;
3. judgment about payoff and friction;
4. truthful uncertainty;
5. and a usable recurring delivery experience.

---

## 4. Initial geography

The initial product serves **Sonoma County / the North Bay**.

The product must treat geography as user-relative.

A Santa Rosa user, Petaluma user, and Healdsburg user may face different travel friction for the same opportunity.

The product must not assume that every user shares the original personal system’s home base.

National coverage is outside the required destination.

---

## 5. Primary user

The primary user is an adult local or regional resident who wants better weekend options without manually researching many fragmented sources.

The product must support different life situations without permanently segmenting users into rigid identities.

The same person may be:

- solo;
- with a partner;
- with family;
- with friends;
- looking for something active;
- looking for something social;
- keeping spending low;
- or seeking a higher-friction exceptional experience.

Persistent context and current-week intent are separate product concepts.

---

## 6. Primary product surface

The primary product surface is an **Event Radar-owned website**.

A user must be able to use the required product without ChatGPT being the only interface.

ChatGPT-native access is a future candidate extension.

---

## 7. Core product objects

### 7.1 Account

The durable identity through which a person accesses private Event Radar state.

### 7.2 User Context

Persistent personalization data that materially changes what is worthwhile for a user.

It must be capable of representing at least:

- home base;
- interests;
- dislikes;
- activity preferences;
- schedule constraints;
- recurring constraints;
- budget/cost tolerance;
- travel tolerance;
- social posture;
- novelty appetite;
- and relevant accessibility or participation constraints.

### 7.3 Weekend Intent

Temporary instructions that affect one upcoming weekend without overwriting the user’s stable context.

Examples:

- “I am solo this weekend.”
- “Keep it cheap.”
- “My partner is visiting.”
- “I want something active.”
- “I want something social.”
- “I only have Sunday morning.”

### 7.4 Regional Opportunity

An evidence-backed scheduled event or experience within the regional research universe.

A Regional Opportunity is not automatically a recommendation for every user.

### 7.5 Regional Weekend Universe

The shared researched opportunity set for a region and weekend.

It may contain:

- normalized occurrence facts;
- source provenance;
- semantic descriptions;
- experience characteristics;
- interaction structure;
- activity value;
- distinctiveness;
- logistics/friction;
- and explicit uncertainty.

It must remain reusable across users.

### 7.6 Weekend Packet

A personalized decision set produced for one user and one weekend.

### 7.7 Subscription

The durable paid relationship that controls entitlement to the paid Event Radar service.

---

## 8. Governing product flow

The required product flow is:

> **Discover → Join → Personalize → Pay → Research → Curate → Deliver → Decide → Update → Return**

Operationally:

1. the user understands the service;
2. creates an account;
3. supplies persistent personalization context;
4. enters a paid state;
5. Event Radar builds the shared regional universe;
6. Event Radar applies the user’s persistent context and current-week intent;
7. Event Radar generates and stores a Weekend Packet;
8. the user receives notification;
9. the user views the packet on Event Radar;
10. the user updates context or current-week intent when needed;
11. the cycle repeats.

---

## 9. Regional research requirements

### 9.1 Shared regional research

Regional research must be performed once where practical and reused across users.

The product must not repeat the entire discovery process independently for every subscriber.

### 9.2 User-neutral shared layer

The shared Regional Weekend Universe must not encode one private user’s preference model as regional truth.

The shared layer may describe what an experience is and what properties it has.

Per-user judgment belongs in personalization.

### 9.3 Multiple discovery inputs

The product must support:

- known structured or semi-structured local sources; and
- complementary discovery for opportunities missed by those sources.

Zero complementary discoveries is valid.

Padding is not.

### 9.4 Provenance

Material event facts should retain source provenance sufficient for traceability.

### 9.5 Dynamic facts

The product must recognize that the following may require current verification:

- ticket availability;
- volatile pricing;
- closures;
- trail access;
- current weather;
- current hours;
- parking availability;
- and other short-lived conditions.

---

## 10. Personalization requirements

### 10.1 Meaningful differentiation

Users with materially different context must be capable of receiving materially different packets from the same Regional Weekend Universe.

### 10.2 Persistent versus temporary context

The system must distinguish persistent User Context from Weekend Intent.

### 10.3 Editability

Users must be able to update persistent context that affects future recommendations.

### 10.4 Non-fabrication

The product must not invent unsupported personal attributes.

### 10.5 Friction-aware judgment

Recommendation judgment must account for:

- cost;
- travel;
- schedule;
- commitment;
- solo practicality;
- and other relevant friction

relative to the payoff of the experience.

Exceptional experiences may survive high friction.

---

## 11. Curation requirements

The final curation stage must:

- independently judge the shared opportunity universe for the specific user;
- produce a finite high-signal set;
- avoid quota padding;
- preserve exceptional high-friction options when justified;
- avoid treating crowds, alcohol, venues, or category labels as automatic social value;
- distinguish co-presence, circulation, natural interaction, and structured/repeated interaction;
- and preserve useful uncertainty.

The user remains the final decision-maker.

---

## 12. Weekend Packet requirements

Each packet must be associated with:

- one user;
- one weekend;
- the personalization context used;
- and the relevant Regional Weekend Universe.

The packet must present enough information for the user to understand:

- what the option is;
- when;
- where;
- approximate price when known;
- why it fits;
- important experience value;
- relevant social/interaction structure;
- solo fit when relevant;
- travel/commitment friction;
- tradeoffs;
- and important unknowns.

The packet is not required to be an exhaustive local calendar.

The packet is not a rigid itinerary.

---

## 13. Website requirements

The Event Radar website must support:

- public product explanation;
- account creation;
- sign-in/sign-out;
- onboarding;
- user-context management;
- Weekend Intent entry or editing;
- subscription state;
- current Weekend Packet viewing;
- retained packet history;
- basic account settings;
- and subscription management.

The exact visual design may evolve.

The required user journeys may not be omitted.

---

## 14. Delivery and recurrence

Event Radar is a recurring weekend service.

The product must:

- create a new packet on a predictable weekly cadence;
- notify the user when the packet is available;
- make the packet available through the Event Radar web product;
- persist the packet;
- and support return use in subsequent weeks.

Email is the required initial notification/delivery channel.

Additional channels are optional.

---

## 15. Paid relationship

The product must support a legitimate paid subscription relationship.

A user must be able to:

- enter a paid state;
- have entitlement recognized;
- understand the current subscription state;
- cancel or end the relationship through a reasonable self-service flow;
- and have access follow the subscription state.

**Commercial implementation:** Stripe Billing.

The exact public price is not fixed by this artifact and may be set immediately before paid-beta activation without Product Definition revision.

---

## 16. Product ownership and persistence

Event Radar must durably persist, at minimum:

- account identity reference;
- User Context;
- Weekend Intent;
- subscription state;
- Regional Weekend Universes;
- Regional Opportunities;
- Weekend Packets;
- packet-to-context provenance sufficient to reproduce or audit decisions;
- and operational state required for recurring delivery.

Durable product state must not live solely in ChatGPT, Telegram, Markdown files, or ephemeral GitHub Actions runners.

---

## 17. Privacy and authorization

The product must ensure that normal users cannot access another user’s:

- context;
- Weekend Intent;
- subscription state;
- packet history;
- or other private account state.

External conversational or AI interfaces must not receive unrestricted database access.

Secrets and privileged credentials must not be exposed to normal clients.

---

## 18. Failure and degraded-state behavior

The product must distinguish:

- successful regional research;
- partial regional research;
- unavailable regional research;
- successful personalization;
- partial personalization;
- and unavailable personalization.

A partial or fallback output must not be labeled as a normal fully successful packet.

Where possible:

- one source failure should not erase successful source results;
- one optional discovery failure should not destroy the entire packet;
- one failed personalization job should not corrupt other users’ packets;
- and previously persisted product state should survive transient provider failure.

Truthful degradation is preferred to fabricated completion.

---

## 19. Quality standards

### 19.1 Usefulness

The packet should materially reduce weekend research burden.

### 19.2 Relevance

Meaningfully different users can receive meaningfully different results.

### 19.3 Discovery

The product can surface worthwhile opportunities ordinary browsing may miss.

### 19.4 Factual integrity

The product does not invent event existence, schedule, location, price, availability, access, or similar operational facts.

### 19.5 Uncertainty honesty

Unknowns remain visibly unknown.

### 19.6 Repeatability

The product can run as a recurring service without rebuilding state manually each week.

### 19.7 Understandability

A paying user can understand the service and packet without learning the internal architecture.

### 19.8 Cost awareness

The system must retain per-stage AI usage/cost telemetry and be capable of identifying abnormal cost growth.

---

## 20. Required external services

The required destination may use external services, but Event Radar remains authoritative for its product state.

The accepted initial service set is:

- **OpenAI Responses API** — semantic analysis, web discovery, personalization;
- **Open-Meteo** — weather;
- **Supabase** — managed PostgreSQL and authentication;
- **Stripe** — billing/subscriptions;
- **Resend** — email delivery;
- **Vercel** — public web application;
- **Render** — backend/API hosting;
- **GitHub Actions** — scheduled batch jobs and CI during the initial product lifecycle.

Provider replacement does not require Product Definition revision if required behavior remains intact.

---

## 21. Product readiness criteria

The Product Definition is satisfied when an external user can independently:

1. understand Event Radar;
2. create an account;
3. provide personalization context;
4. pay;
5. receive a personalized weekend packet;
6. view the packet on Event Radar;
7. return later and access retained packet history;
8. update relevant context;
9. set current-week intent;
10. manage the subscription;
11. receive future packets on schedule;
12. and use the product without routine builder intervention.

The system must additionally prove:

- multi-user privacy;
- reusable shared research;
- per-user personalization;
- truthful degradation;
- recurring operation;
- paid entitlement correctness;
- and durable product state.

---

## 22. Product success evidence

The product must be capable of producing evidence relevant to:

- paid conversion;
- packet delivery;
- packet viewing;
- repeat use;
- subscription retention;
- recommendation usefulness;
- and whether users act on recommendations.

No numeric market-success threshold is fixed here.

---

## 23. Product-level non-goals

The required destination does not include:

- national coverage;
- a native mobile application;
- a social network;
- user reviews;
- venue dashboards;
- an advertising marketplace;
- a restaurant database;
- a coffee database;
- comprehensive local-place search;
- geographic outing chaining;
- advanced maps;
- saved favorites;
- partner/family profile systems;
- a custom chat UI;
- or a ChatGPT Plugin.

These remain future product territory.

---

## 24. Governing status

**ACCEPTED / GOVERNING — VERSION 1.0**

This artifact defines the required destination product.

Any future change to required capability, core product object, major user flow, product boundary, privacy expectation, or readiness criterion requires explicit Product Definition revision.
