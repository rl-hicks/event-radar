# Event Radar — Product Phase Roadmap Artifact

**Version:** 1.0  
**Status:** ACCEPTED / GOVERNING  
**Accepted:** 2026-10-02  
**Artifact type:** Product Phase Roadmap  
**Upstream authority:** Event Radar — Project Definition v1.0; Event Radar — Product Definition v1.0  
**Project owner:** Robot

---

## 1. Authority

This artifact governs staged product maturity.

It defines what becomes true of the product at each version.

It does not define detailed engineering implementation.

The initial product path is:

> **V1 — Paid Personalized Beta**  
> **V2 — Repeatable Weekend Service**  
> **V3 — Launch-Capable Local Product**

The roadmap stops at V3 because V3 satisfies the current Product Definition.

---

# V1 — Paid Personalized Beta

## 2. Purpose

V1 proves the essential commercial product loop:

> **An external user can pay for Event Radar, provide personal context, and receive a genuinely personalized weekend packet built from shared regional research.**

V1 is a real product state.

It is not a prototype, mockup, private Telegram workflow, or manually assembled report.

## 3. Required V1 state

At V1 completion an external beta user can:

1. understand what Event Radar does;
2. create and access an account;
3. enter a paid state;
4. complete onboarding;
5. provide sufficient personal context;
6. receive a personalized Weekend Packet;
7. view that packet on an Event Radar-owned website;
8. receive email notification;
9. and make a real weekend decision from it.

The system must additionally support more than one user without leaking private state or applying one user’s preference model to everyone.

## 4. V1 capabilities

V1 requires:

- public landing/product explanation;
- account identity;
- authentication;
- protected user state;
- onboarding;
- persistent initial User Context;
- real payment;
- shared Regional Weekend Universe generation;
- per-user personalization;
- Weekend Packet persistence;
- current packet web view;
- email notification;
- basic factual/uncertainty integrity;
- and multi-user isolation.

## 5. V1 acceptance evidence

V1 closes only when:

- at least one external user enters a real paid state;
- the user receives a real personalized packet;
- the packet is derived from shared regional research plus that user’s context;
- a second materially different test user can receive a meaningfully different packet from the same shared universe;
- private state is isolated;
- the packet is accessible on Event Radar;
- email notification works;
- and there is credible evidence that the product affected a real weekend decision.

One paying user proves the loop exists.

It does not prove the business is validated.

## 6. V1 failure conditions

V1 remains open if:

- the builder is still the only working user;
- payment is simulated;
- packets are generic;
- shared research is contaminated by the original user’s private taste model;
- the website is not the owned product surface;
- cross-user privacy fails;
- or the user requires the builder to interpret or manually assemble the packet.

## 7. V1 exclusions

V1 does not require:

- packet history;
- rich profile editing;
- recurring Weekend Intent controls;
- subscription self-service;
- retention analytics;
- restaurant/coffee data;
- geographic chaining;
- maps;
- ChatGPT integration;
- or mobile apps.

---

# V2 — Repeatable Weekend Service

## 8. Purpose

V2 proves Event Radar is a recurring product relationship rather than a one-time paid experiment.

The core question is:

> **Can the same user continue using Event Radar across multiple weekends without starting over or relying on the builder to maintain ordinary state?**

## 9. Required V2 state

At V2 completion the user can:

- keep persistent User Context across weekends;
- edit that context;
- provide Weekend Intent for a specific week;
- receive packets predictably each week;
- receive recurring email notification;
- access packet history;
- understand and manage subscription state;
- and continue using the product without repeating onboarding.

## 10. V2 capabilities

V2 adds or deepens:

- self-service profile/context editing;
- temporary Weekend Intent;
- predictable recurring packet cycle;
- packet archive/history;
- subscription continuity and cancellation;
- recurring entitlement handling;
- usage/engagement evidence;
- and clear user-facing degraded-state behavior.

## 11. V2 acceptance evidence

V2 closes only when:

- the same user can move through multiple weekly cycles;
- persistent context remains correct;
- Weekend Intent affects the intended week without corrupting stable context;
- packet history is retained;
- subscription state persists correctly;
- recurring delivery works;
- degraded states are visible;
- and the product can measure whether users are returning.

## 12. V2 failure conditions

V2 remains open if:

- users repeatedly re-enter stable context;
- temporary instructions overwrite durable context;
- delivery is unpredictable;
- packet history is unreliable;
- subscription state is inconsistent;
- or ordinary use still requires routine manual state maintenance by the builder.

## 13. V2 exclusions

V2 still does not require:

- local-place databases;
- outing chaining;
- real-time planning;
- ChatGPT integration;
- advanced maps;
- new regions;
- or mobile apps.

---

# V3 — Launch-Capable Local Product

## 14. Purpose

V3 completes the current Product Definition.

Its core question is:

> **Can Event Radar operate as a coherent, understandable, dependable local subscription product without the builder being part of every normal user journey?**

## 15. Required V3 state

At V3 completion the user can independently:

1. discover the product;
2. join;
3. personalize;
4. pay;
5. receive recurring packets;
6. view current and retained packets;
7. update persistent context;
8. set Weekend Intent;
9. manage subscription state;
10. encounter truthful degraded states;
11. and continue using the service without routine builder intervention.

## 16. V3 capabilities

V3 completes:

- full normal account lifecycle;
- robust authorization boundaries;
- complete shared-research/per-user-personalization separation;
- reliable recurring job behavior;
- polished Weekend Packet usability;
- production failure/degradation handling;
- operational monitoring;
- cost visibility;
- supportable subscription lifecycle;
- and builder-independent normal operation.

## 17. V3 acceptance evidence

V3 closes only when the Product Definition’s readiness criteria are satisfied and verified.

Evidence must include:

- public usability;
- multi-user correctness;
- shared research reuse;
- personalized packet integrity;
- recurring operation;
- paid entitlement correctness;
- private-state isolation;
- truthful degradation;
- packet history;
- and normal operation without manual packet assembly.

## 18. V3 failure conditions

V3 remains open if any required Product Definition capability is absent or normal operation remains materially dependent on the builder.

## 19. V3 exclusions

Completing V3 does not require:

- ChatGPT Plugin;
- restaurant/coffee database;
- geographic chaining;
- maps;
- saved favorites;
- partner/family profiles;
- national coverage;
- social features;
- or mobile apps.

Those belong to future product development.

---

## 20. Requirement-to-version map

| Product capability | First required |
|---|---:|
| Public product explanation | V1 |
| Account + authentication | V1 |
| Basic private-state isolation | V1 |
| Real payment | V1 |
| Initial persistent User Context | V1 |
| Shared Regional Weekend Universe | V1 |
| Per-user personalization | V1 |
| Current packet web view | V1 |
| Email notification | V1 |
| Basic factual/uncertainty integrity | V1 |
| Editable persistent context | V2 |
| Weekend Intent | V2 |
| Predictable weekly recurrence | V2 |
| Packet history | V2 |
| Subscription self-service | V2 |
| Repeat-use evidence | V2 |
| Clear degraded-state UX | V2 |
| Full account lifecycle | V3 |
| Full operational hardening | V3 |
| Builder-independent normal operation | V3 |
| Complete Product Definition readiness | V3 |

---

## 21. Progression rule

A version closes only when its required product state actually exists and acceptance evidence is available.

Do not build later-version breadth to avoid confronting failure of an earlier value claim.

If V1 fails to prove paid personalized value, the correct response is to reconsider the product—not automatically to build V2.

If V2 fails to prove repeat use, the correct response is not automatically to polish toward V3.

---

## 22. Governing status

**ACCEPTED / GOVERNING — VERSION 1.0**

This artifact governs product staging.

The final destination remains controlled by the Product Definition.
