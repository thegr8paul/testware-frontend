<!--
  This file IS the demo-day deck. It renders as animated slides in the app
  under sidebar -> Read Me (component: components/deck/).

  HOW SLIDES WORK
  - Separate every slide with a line of three dashes.
  - #### text   kicker (small caps line above the title)
  - ## text     slide title  (use *asterisks* for the accent colour, e.g. testware*.dev*)
  - ### text    a supporting sub-line
  - - item      bullet  (**bold** and [links](https://…) work)
  - > text      a quote / pull-out
  - ![Caption](placeholder-a.svg)   an image; files live in components/deck/
  - Force a layout with an HTML comment "layout: NAME" as the slide's first
    line. NAME is one of: title, section, content, media, split, quote.

  IMAGE PLACEHOLDERS
  - Every ![...](placeholder-*.svg) is a labelled grey box saying what
    pictogram / diagram / screenshot belongs there. Replace the .svg file in
    components/deck/ (keep the filename) or repoint the reference.

  STATUS: draft of the 10-slide pitch. [NEEDS INPUT] / [VISUAL] markers flag
  the spots left for manual follow-up.
-->

## testware*.dev*
### One-stop webshop for digital-twin-based everything, everywhere, all at once.

![Hero visual](placeholder-hero.svg)

---

<!-- layout: media -->

#### Why now · 01
## Every industry is becoming software-defined

- Three shifts at once: electrification, automation, digitalisation
- Across auto/aero, energy, infrastructure, manufacturing, agriculture, life sciences
- Software-defined plants — vehicles, grids, batteries, robots, medical devices — mean more code, more data, more complexity

![Pictogram grid — the verticals](placeholder-verticals.svg)

---

<!-- layout: media -->

#### Why now · 02
## Ship faster — and prove it's safe

- Shorter release cycles collide with tighter regulation: ISO 26262 · DO-178C · IEC 62304
- The response: left-shifted, test-driven development
- **€50B** EU digital-twin market by 2030

Source: [NEEDS INPUT — citation URL for the "€50B EU digital-twin market by 2030" figure]

![Market-size diagram](placeholder-market.svg)

---

<!-- layout: media -->

#### How · models
## Right fidelity for the right problem

- Multiscale & multiphysics, computational X-mechanics
- Systems biology, controls & systems engineering
- ML, reduced-order modelling, topological (CAD, point clouds)

![VISUAL — modelling-fidelity spectrum diagram](placeholder-fidelity.svg)

---

<!-- layout: media -->

#### How · simulators & workflows
## From models to real-time testing

- Real-time targets, sensors, power electronics, FPGAs
- Industrial protocols: CAN · ARINC · FlexRay
- Enables X-in-the-Loop, rapid prototyping, predictive maintenance, virtual commissioning, restbus simulation

![VISUAL — X-in-the-Loop test setup](placeholder-xil.svg)

---

<!-- layout: media -->

#### What · illustrative outputs
## Three example workflows our tool generates

Illustrative outputs from our own LLM+RAG pipeline — saved generations, not client projects.

- ICME-based digital twin for material-failure prediction
- Building digital twin from an IFC model
- Patient digital twin

![VISUAL — three generated flowcharts; swap in real tool output](placeholder-cases.svg)

---

<!-- layout: media -->

#### The problem
## The on-ramp is missing

- Digital-twin know-how is niche — few people can start from scratch
- Tools are proprietary, expensive, rarely open-source
- Real systems span verticals — materials, building, patient in one place — and integration is hard

![Pictogram — the missing on-ramp](placeholder-gap.svg)

---

<!-- layout: media -->

#### The solution
## A fast, accessible on-ramp

- A structured prompt — industry, application, nature of the project
- LLM+RAG generates a workflow description, a flowchart, and tool suggestions from our curated database
- Edit the flowchart, save it as your own workflow

![Screenshot — prompt and tags to workflow, flowchart, tools](placeholder-solution.svg)

---

<!-- layout: media -->

#### Product · now & next
## Working today — and where it goes

- **Now:** prompt bar + category tags → enhanced prompt → generated workflow description, flowchart and suggested tools → edit and save; every save grows our workflow dataset
- **Next:** individual tools connect as live, executable nodes inside a saved flowchart — e.g. an Airflow-based car simulation
- **Next:** visualise, understand and eventually run full digital-twin workflows in the tool

![Diagram — now to later, suggestion to executable node](placeholder-roadmap.svg)

---

<!-- layout: media -->

#### Business model & ask
## Grow now, monetise later

- **Today:** growth over revenue — maximise users creating and saving workflows; build traffic and the dataset
- **Later:** monthly subscription to understand, visualise and execute digital-twin workflows
- **Later:** vendor lead-gen — tools plugged in as nodes become qualified leads — and the workflow dataset as an asset in its own right

> We're looking for early users and honest feedback — and open to partnership and investment conversations.

[NEEDS INPUT — confirm exact ask phrasing]

![Pictogram — growth now, monetise later](placeholder-model.svg)
