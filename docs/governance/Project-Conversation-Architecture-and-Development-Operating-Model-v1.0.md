# Project Conversation Architecture & Development Operating Model

**Version 1.0**

## 1. Purpose

This artifact defines how ChatGPT conversations cooperate to take a project from an undeveloped idea through governed definition, staged engineering, implementation, handoff, historical tracking, and eventual completion.

It governs the **conversation architecture and operating model** used around the project artifacts defined in `Project Artifacts v2`.

`Project Artifacts v2` defines what the project artifacts are and what authority each artifact holds.

This document defines how the conversations create, review, execute against, hand off, and preserve those artifacts.

The central model is:

> **The governing artifacts define the project. The conversations operate the project.**

Conversations are working environments. They are not authoritative merely because something was said inside them. Important decisions become project truth through the appropriate governing artifact, accepted execution roadmap, handoff, or Project Tracker record.

---

# 2. The Operating Architecture

The project uses five primary conversation roles:

1. **Kickstarter Conversation**
2. **Project Manager Conversation**
3. **Engineering Execution Conversation**
4. **Branched Execution Conversation**
5. **Project Tracker Conversation**

These roles cooperate with the project artifact chain:

**Project Definition**  
↓  
**Product Definition**  
↓  
**Product Phase Roadmap**  
↓  
**Engineering Phase Map**  
↓  
**Active Engineering Execution Roadmap**  
↓  
**Implementation and verification**  
↓  
**Phase Handoff / Closeout**  
↓  
**Project Tracker**  
↓  
**Next Engineering Execution Roadmap**

The conversation architecture exists to move work through this chain without forcing one conversation to carry every type of reasoning, implementation detail, and historical context.

---

# 3. Governing Principle: Separate Authority from Working Context

The project must distinguish between:

- what the project **is**;
- what the product **must become**;
- how product maturity is **staged**;
- how engineering is **mapped**;
- how the current phase is **executed**;
- and what **actually happened**.

The governing artifacts own those meanings.

Conversations are responsible for operating within them.

A conversation may discover that an artifact should change. It may recommend or draft that change. It may not silently redefine upstream project commitments through implementation.

The project owner retains final authority over changes to governing project and product commitments.

---

# 4. Project Formation: The Kickstarter Conversation

## 4.1 Role

The Kickstarter is the project-formation conversation.

It begins before the project is fully defined.

The user may arrive with an idea, problem, product concept, rough technical concept, desired outcome, disconnected thoughts, or only a general sense of something worth building.

The Kickstarter is allowed to be exploratory, iterative, permissive, and messy.

Its job is to absorb that ambiguity and progressively turn it into governed project structure.

## 4.2 Kickstarter responsibilities

The Kickstarter should:

- help the user explain what they are trying to accomplish;
- surface hidden assumptions and contradictions;
- distinguish desired outcomes from proposed mechanisms;
- explore alternative interpretations when useful;
- clarify boundaries and non-goals;
- identify decisions that are genuinely settled;
- preserve decisions that are intentionally open;
- challenge premature implementation commitments;
- and gradually produce the initial governing artifact set.

The Kickstarter is a thought partner during project formation.

It is not merely a form that converts a prompt into a static document.

## 4.3 Initial artifact sequence

The Kickstarter normally develops the initial project artifacts in this order:

1. **Project Definition Artifact**
2. **Product Definition Artifact**
3. **Product Phase Roadmap Artifact**
4. **Engineering Phase Map Artifact**
5. **E0 Engineering Execution Roadmap**

The artifacts do not need to be produced in one uninterrupted session.

The user may create one artifact, take it to the Project Manager for review, return to the Kickstarter with revisions, and then continue to the next artifact.

The goal is not speed. The goal is a coherent initial project architecture.

## 4.4 Why E0 is created in Kickstarter

E0 is the one detailed Engineering Execution Roadmap that may be created before any engineering execution conversation has completed.

There is no previous engineering phase available to create it.

The Kickstarter therefore uses the accepted governing artifacts, chosen technical foundation, and known starting state to draft the initial E0 Engineering Execution Roadmap.

After E0, the predecessor execution conversation becomes responsible for drafting the next Engineering Execution Roadmap because it possesses better implementation context than the Kickstarter.

## 4.5 Authority

The Kickstarter may draft governing artifacts, but a draft is not authoritative merely because it exists.

The Project Manager may review the artifact for coherence and consistency.

The project owner accepts, rejects, or revises governing changes.

Once accepted, the artifact becomes part of the project's governing source set.

---

# 5. Project Control: The Project Manager Conversation

## 5.1 Role

The Project Manager is the project's primary continuity and coordination conversation after project formation begins.

It maintains the project-wide operational picture.

It should understand the current governing artifacts, current project state, accepted phase handoffs, material unresolved decisions, active execution conversations, known reported branches, current blockers, and the next required transition.

The Project Manager is both a coordinator and a strategic thought partner.

It is not limited to acting as a scope gatekeeper.

## 5.2 Responsibilities

The Project Manager should:

- review proposed governing artifacts;
- detect conflicts between artifacts;
- distinguish project, product, roadmap, engineering, and execution decisions;
- maintain continuity as the project moves between conversations;
- help determine where a piece of work belongs;
- prevent silent scope or authority drift;
- identify when upstream artifacts need revision;
- reconcile phase closeouts with the governing source set;
- help the user reason through consequential project decisions;
- create conversation initializers for execution conversations;
- create or update handoff instructions when needed;
- and orient the next phase from the accepted project state.

The Project Manager may perform small coordination-level work directly.

Substantive phase implementation should normally occur in an Engineering Execution Conversation.

## 5.3 Conversation initializer responsibility

When an Engineering Execution Roadmap is accepted, the Project Manager creates the initializer for the corresponding Engineering Execution Conversation.

The initializer should communicate:

- project identity;
- execution-conversation role;
- active engineering phase;
- authoritative artifacts;
- relevant current baseline;
- phase objective;
- required exit state;
- important constraints;
- explicit exclusions;
- decision and escalation boundaries;
- mission-intent autonomy;
- verification expectations;
- handoff requirements;
- and required closeout outputs.

The initializer is a control packet.

It should orient the execution conversation without trying to replace the governing artifacts themselves.

Where practical, it should point to authoritative artifacts rather than duplicate large amounts of content that can later drift.

## 5.4 Visibility limitation

The Project Manager does not automatically know everything that happens in every branched conversation.

Important branch outcomes must be explicitly returned through handoffs or otherwise supplied to the Manager.

No project architecture should depend on invisible cross-conversation propagation.

---

# 6. Engineering Execution Conversations

## 6.1 Role

An Engineering Execution Conversation owns one active engineering phase.

Examples:

- E0 Execution
- E1 Execution
- E2 Execution

It receives a bounded mission through its initializer and active Engineering Execution Roadmap.

Its job is to turn the required phase outcome into verified implementation.

## 6.2 Inputs

An execution conversation should begin with access to the relevant current sources, including the governing project artifacts, active Engineering Execution Roadmap, prior phase handoff where relevant, current repository or implementation baseline, current deployment/data state where relevant, and accepted decisions required for the phase.

It should know both **what the mission is** and **why that mission matters**.

## 6.3 Responsibilities

The execution conversation may:

- inspect the actual system;
- implement;
- debug;
- test;
- deploy;
- investigate;
- revise local plans;
- create bounded branches;
- integrate returned branch work;
- record consequential decisions;
- verify phase requirements;
- and prepare the next phase from the state that actually resulted.

It is an operator, not merely a task checklist.

---

# 7. Mission-Intent Execution

## 7.1 Core doctrine

Engineering Execution Conversations operate under **mission intent, not literal task obedience**.

The active Engineering Execution Roadmap is the best plan available before and during implementation.

It is not a script that overrides evidence.

The execution conversation should understand the mission, required outcome, constraints that must remain true, evidence required for success, and boundaries it may not change independently.

The governing priority is:

> **Intent > required outcome > governing constraints > planned method.**

The planned method is the most disposable layer.

## 7.2 Permitted adaptation

When evidence warrants it, an execution conversation may change local implementation details such as:

- work-package order;
- implementation sequence;
- internal module or file organization;
- debugging approach;
- testing strategy;
- local architecture choices that were not locked upstream;
- bounded libraries or implementation patterns;
- branch structure;
- or another tactical choice.

It should do so when the change better accomplishes the mission while preserving governing requirements.

## 7.3 Escalation boundary

The execution conversation may maneuver within the mission.

It may not silently redefine the mission.

Material changes must be escalated when they would alter:

- project identity or purpose;
- Product Definition commitments;
- Product Phase Roadmap scope;
- the mission of the active engineering phase;
- locked technical-stack decisions;
- major governing architecture commitments;
- commercial commitments;
- privacy or ownership boundaries;
- or another upstream requirement outside the execution conversation's authority.

When such a conflict appears, the execution conversation should stop affected dependent work, explain the conflict, identify the minimum blocking decision, provide relevant evidence and options, and return the decision to the Project Manager / project owner.

## 7.4 Traceability

Autonomy must remain traceable.

If execution materially deviates from the original roadmap, the phase handoff should record:

- what was originally planned;
- what evidence changed the plan;
- what adaptation was made;
- why that adaptation better served the mission;
- and what result followed.

The goal is autonomy without chaos.

---

# 8. Branched Execution Conversations

## 8.1 Purpose

Execution conversations may branch when a subproblem deserves its own focused context.

Examples include UI or visual design, database design, provider investigation, debugging a difficult subsystem, generation-quality work, migration design, security review, or another bounded problem.

Branching prevents the parent execution conversation from becoming overloaded with deep side investigations that can be isolated.

## 8.2 Authority

A branch inherits its mission and authority from its parent execution conversation.

It may make local decisions within the bounded subproblem.

It may not independently redefine project, product, roadmap, or phase commitments.

A branch is a subordinate working context, not a new governing authority.

## 8.3 Nested branches

Nested branches are allowed when genuinely useful.

Every child branch remains responsible to its direct parent.

The handoff chain should remain explicit.

## 8.4 Branch completion requirement

When a branch completes its work, it must be able to produce a **Branch Handoff** for the parent execution conversation.

The handoff should reconstruct the useful outcome without forcing the parent to reread the entire branch.

A Branch Handoff should normally include:

- assigned problem or objective;
- relevant starting context;
- work performed;
- important sequence of investigation or implementation;
- decisions made;
- rationale for consequential decisions;
- code, artifacts, designs, or system changes produced;
- tests or evidence;
- failures or rejected approaches that materially affected the result;
- unresolved issues;
- deferred work;
- integration considerations;
- and the resulting state.

The handoff should be concise enough to ingest, but complete enough to preserve consequential reasoning.

## 8.5 Integration rule

A branch result is not considered integrated merely because the branch finished.

The handoff must return to the parent execution conversation, and the parent remains responsible for incorporating the branch outcome into the phase.

---

# 9. Engineering Phase Closeout

## 9.1 Two required closeout outputs

When a main Engineering Execution Conversation finishes its phase, it should normally produce two outputs:

1. **Phase Handoff / Closeout**
2. **Draft Engineering Execution Roadmap for the next phase**

The final engineering phase is the exception: if there is no next engineering phase, it produces the appropriate project-completion, maintenance, or future-work handoff instead.

## 9.2 Phase Handoff / Closeout

The closeout is the factual, cohesive account of what the phase actually accomplished.

It should normally capture:

- phase starting state;
- intended objective;
- governing requirements;
- major work performed;
- meaningful implementation sequence;
- branches created;
- branch outcomes integrated;
- consequential decisions and their rationale;
- deviations from the original execution roadmap;
- problems encountered;
- how important failures were resolved;
- implementation produced;
- migrations or deployment changes where relevant;
- verification and evidence;
- phase-gate disposition;
- unresolved blockers;
- known limitations;
- deliberate deferrals;
- current repository/system/deployment state;
- and implications for the next phase.

The closeout is not a raw transcript dump.

It should be a reconstruction of the phase useful to a later conversation that was not present while the work happened.

## 9.3 Handoff audiences

The Phase Handoff is intended to return to:

- the **Project Manager**, for project-wide reconciliation and next-phase coordination;
- and the **Project Tracker**, for durable historical memory.

The same core closeout may serve both audiences.

---

# 10. Rolling Creation of Engineering Execution Roadmaps

## 10.1 Core rule

Detailed Engineering Execution Roadmaps are created **one phase at a time**.

Do not precompute detailed E1, E2, E3, and E4 plans before earlier phases have been implemented.

The project may know the high-level direction through the Engineering Phase Map.

Detailed implementation planning waits until the relevant phase becomes next.

## 10.2 Predecessor-drafts-successor model

After E0 is completed, the E0 Execution Conversation drafts the E1 Engineering Execution Roadmap.

After E1 is completed, E1 drafts E2.

After E2 is completed, E2 drafts E3.

And so on.

The reason is practical:

> The conversation that just implemented the current phase has the richest context about what the system actually became.

It knows which assumptions held, which failed, what implementation choices were made, what architecture now exists, what defects remain, what work became unnecessary, what new constraints appeared, and what the next phase is really starting from.

## 10.3 Inputs to the next-phase draft

The next Engineering Execution Roadmap should be drafted from:

- Project Definition;
- Product Definition;
- Product Phase Roadmap;
- Engineering Phase Map;
- current phase closeout;
- integrated Branch Handoffs;
- actual resulting repository/system state;
- accepted technical decisions;
- known blockers and limitations;
- and the next phase's high-level objective.

## 10.4 Draft, not unilateral authority

The predecessor execution conversation drafts the next roadmap.

It does not independently redefine the next phase.

The draft returns to the Project Manager and project owner for reconciliation against the governing artifacts.

Once accepted, the next Engineering Execution Roadmap becomes the active plan.

The Project Manager then creates the initializer for the new execution conversation.

---

# 11. The Project Tracker Conversation

## 11.1 Role

The Project Tracker is the project's durable factual memory.

It answers:

> What actually happened, why did consequential decisions happen, and what state did they leave behind?

The Tracker is not responsible for deciding what the project should do next.

That belongs to the Project Manager and governing artifacts.

## 11.2 What the Tracker preserves

The Tracker should preserve historically useful information such as:

- governing artifact creation and revision;
- accepted project and product decisions;
- phase starts and closeouts;
- important implementation outcomes;
- consequential technical decisions and their recorded rationale;
- significant branches where their outcomes affected the project;
- verified baselines;
- deployments;
- migrations;
- test evidence;
- known limitations;
- deliberate deferrals;
- blockers;
- and phase transitions.

## 11.3 Narrative fidelity

The Tracker should be factual, but factual does not mean context-free.

If a source handoff records why a consequential decision was made, that rationale is historical fact and should be preserved.

The Tracker should not invent motives or reconstruct unsupported reasoning.

It should distinguish observed fact, accepted decision, recorded rationale, unresolved uncertainty, and later interpretation.

## 11.4 Tracker versus handoff

A Phase Handoff is a detailed closeout produced by the execution conversation that lived through the work.

The Project Tracker is the cumulative project history that ingests those closeouts and other accepted project records.

The Tracker should not require every low-level action to be logged individually if a later verified handoff captures the meaningful history more accurately.

---

# 12. Handoffs Are First-Class Project Objects

The project should treat handoffs as explicit continuity mechanisms.

They exist because conversations are deliberately segmented.

There are two primary handoff types.

## Branch Handoff

**From:** Branched Execution Conversation  
**To:** Parent Execution Conversation

Purpose:

> Return a solved or investigated subproblem to the phase that owns it.

## Phase Handoff / Closeout

**From:** Engineering Execution Conversation  
**To:** Project Manager and Project Tracker

Purpose:

> Return the completed phase, its decisions, evidence, resulting state, and limitations to the project-wide control and memory layers.

A handoff should preserve consequential context without reproducing the entire conversation.

---

# 13. Conversation Initializers

Conversation initializers implement roles defined by this artifact.

The initializers are subordinate to this governing operating model.

At minimum, the project maintains initializer prompts for:

- Kickstarter;
- Project Manager;
- Project Tracker.

Execution initializers are generated dynamically by the Project Manager for the active phase rather than relying on one timeless generic E1/E2/E3 prompt.

A good initializer should establish:

- role;
- mission;
- authority;
- governing sources;
- current state;
- scope;
- allowed autonomy;
- escalation rules;
- expected deliverables;
- handoff behavior;
- and stopping conditions.

An initializer should not become a second copy of every governing artifact.

Its job is to orient the conversation to the sources that actually hold authority.

---

# 14. Source-of-Truth Rules

## 14.1 Governing artifacts over conversation memory

If remembered conversational context conflicts with an accepted governing artifact, the artifact controls unless a later owner-approved decision superseded it.

## 14.2 Current accepted version over historical version

Later accepted versions supersede older versions within their authority.

Historical artifacts remain useful for provenance but do not govern current work.

## 14.3 Actual execution state belongs in handoffs and Tracker

Plans do not prove implementation.

A roadmap says what should happen.

A verified closeout and Tracker record say what actually happened.

## 14.4 No invisible branch assumptions

A parent conversation, Project Manager, or Tracker should not assume knowledge of branch work that has not been returned or otherwise supplied.

Explicit handoff is the default continuity mechanism.

---

# 15. Decision Routing

When a decision appears, route it to the layer that owns it.

## Project-level change

Examples: purpose, project identity, fundamental scope, durable principle.

Route to:

**Project Manager + project owner**, with Project Definition revision if accepted.

## Product-level change

Examples: required product capability, core user behavior, major product object, product boundary.

Route to:

**Project Manager + project owner**, with Product Definition revision if accepted.

## Product-phase sequencing change

Examples: moving a capability between versions, splitting a milestone, adding or removing a product milestone.

Route to:

**Project Manager + project owner**, with Product Phase Roadmap revision if accepted.

## Engineering-map change

Examples: locked stack, major architecture direction, engineering phase structure, phase-to-product mapping.

Route to:

**Project Manager + project owner**, with Engineering Phase Map revision if accepted.

## Local execution decision

Examples: implementation sequence, module design, bounded internal library choice, test arrangement, debugging strategy.

Route to:

**Engineering Execution Conversation**, provided upstream constraints remain intact.

---

# 16. The Full Project Lifecycle

## Formation

Kickstarter  
→ explore the idea  
→ Project Definition  
→ Product Definition  
→ Product Phase Roadmap  
→ Engineering Phase Map  
→ E0 Engineering Execution Roadmap

## Review and activation

Project Manager  
→ review and reconcile artifacts  
→ owner accepts governing state  
→ create E0 execution initializer

## Execution

E0 Execution Conversation  
→ inspect actual baseline  
→ execute under mission intent  
→ branch where useful  
→ receive Branch Handoffs  
→ integrate  
→ verify E0

## Closeout

E0 Execution Conversation  
→ produce E0 Phase Handoff / Closeout  
→ draft E1 Engineering Execution Roadmap

## Reconciliation

Project Manager  
→ ingest E0 closeout  
→ compare E1 draft against governing artifacts  
→ resolve necessary decisions with owner  
→ accept/revise E1 roadmap  
→ create E1 initializer

Project Tracker  
→ ingest accepted E0 history

## Repeat

E1 Execution  
→ branches  
→ handoffs  
→ integration  
→ verification  
→ E1 closeout  
→ draft E2

Then continue until the required Product Phase Roadmap state has been delivered and the project reaches its intended completion or launch-capable state.

---

# 17. Project Completion

A project is not complete merely because the final planned engineering task was performed.

Completion should reconcile:

- Project Definition;
- Product Definition;
- Product Phase Roadmap;
- Engineering Phase Map;
- phase closeouts;
- verified implementation;
- known limitations;
- and final project state.

The Project Manager should help determine whether the governing completion conditions have actually been satisfied.

The final execution conversation should produce a final closeout rather than a next-phase Engineering Execution Roadmap when no next phase is scheduled.

Future work may later be admitted through an explicit project or product decision rather than silently extending the completed roadmap forever.

---

# 18. Anti-Patterns

The operating model should resist the following failure modes.

## One giant conversation

Do not force project formation, project management, implementation, side investigations, and historical tracking into one endlessly growing context.

## Premature detailed planning

Do not produce detailed distant-phase implementation plans before earlier phases have encountered reality.

## Literal roadmap obedience

Do not continue a broken implementation approach merely because it appears in the roadmap.

Preserve the mission, not obsolete tactics.

## Silent scope mutation

Do not allow an execution conversation to redefine the product while solving a technical problem.

Escalate upstream changes.

## Orphan branches

Do not allow valuable branch work to disappear without a handoff to its parent.

## Transcript-as-history

Do not treat raw chat history as the project's only memory.

Create explicit closeouts and maintain the Project Tracker.

## Plan-as-reality

Do not assume an implementation exists because a roadmap or initializer says it should.

Require evidence.

## Duplicate authority

Do not allow initializer prompts, execution notes, or branch decisions to quietly compete with governing artifacts.

---

# 19. Compressed Operating Model

The conversation architecture can be summarized as:

> **Kickstarter defines the initial project.**

> **Project Manager maintains project-wide coherence and coordinates the work.**

> **Engineering Execution Conversations accomplish one engineering phase under mission intent.**

> **Branched Execution Conversations solve bounded subproblems and return explicit handoffs.**

> **Each completed engineering phase closes itself and drafts the next phase's Engineering Execution Roadmap from actual implementation reality.**

> **Project Manager reconciles that draft with the governing artifacts and creates the next execution initializer.**

> **Project Tracker preserves what actually happened and why consequential decisions were made.**

And the project-development loop is:

> **Explore → define → stage → map → plan the current phase → execute → branch as needed → hand off → verify → close → record → draft the next phase from reality → reconcile → repeat.**

---

# 20. Final Principle

The entire architecture exists to preserve two things at once:

**continuity of intent**  
and  
**freedom to adapt to reality.**

The governing artifacts preserve intent.

The conversation architecture preserves context.

Mission-intent execution preserves engineering judgment.

Handoffs preserve learning across segmented conversations.

The Project Tracker preserves history.

Together they allow a project to remain coherent without requiring every future decision to be known in advance.
