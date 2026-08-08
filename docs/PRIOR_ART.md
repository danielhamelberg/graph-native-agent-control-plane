# Terminology and Prior Art

Research date: 2026-08-08. Scope: authenticated GitHub public-code search plus inspection of the
specific public files linked below. Search indexes are incomplete and change over time.

## Exact-name search

The following case-insensitive exact-phrase searches returned zero indexed public-code matches at
the research date:

- [`"Graph-Native Agent Control Plane"`](https://github.com/search?q=%22Graph-Native+Agent+Control+Plane%22&type=code)
- [`"graph-native agent control plane"`](https://github.com/search?q=%22graph-native+agent+control+plane%22&type=code)
- [`"next level in harness engineering"`](https://github.com/search?q=%22next+level+in+harness+engineering%22&type=code)

That is useful naming evidence, but it does not establish coinage, legal exclusivity, or absence from
unindexed code, publications, talks, trademarks, private repositories, or earlier deleted material.

## Adjacent public usage

The broader language is already in active public use:

- Datawhale China published a chapter titled **“From Harness to Loop to Graph Engineering”** and
  distinguishes the runtime around a model, feedback loops, and graphs coordinating multiple
  execution units. See the
  [immutable GitHub revision](https://github.com/datawhalechina/easy-data-x-ai/blob/806f975375c545366278198d7f7cd5a8ba7e01cd/docs/extra/X6%20%E4%BB%8E%20Harness%20%E5%88%B0%20Loop%EF%BC%8C%E5%86%8D%E5%88%B0%20Graph%20Engineering.md).
- Whim's public harness design says graph engineering makes control flow explicit through bounded
  node roles, known interfaces, and durable lifecycle. See the
  [immutable GitHub revision](https://github.com/ZachDreamZ/whim-ide/blob/01306f64a08d2022c41f3bdaaf05a59f7087489d/docs/agent-harness.md).
- ChainReactors explicitly discusses graph engineering as an emerging, ambiguous term and frames
  its substance as coordination and structure engineering. See the
  [immutable GitHub revision](https://github.com/chainreactors/wiki/blob/7346559c0f634bcd98adfa4bf066eea704c83123/docs/blog/posts/%E9%87%8D%E6%96%B0%E7%90%86%E8%A7%A3%20Graph%20Engineering%EF%BC%9AAgent%20%E5%B7%A5%E7%A8%8B%E5%88%B0%E5%BA%95%E5%8F%91%E7%94%9F%E4%BA%86%E4%BB%80%E4%B9%88%E5%8F%98%E5%8C%96.md).
- ZenML uses **“graph-native harness”** to characterize LangGraph in a product comparison. See the
  [immutable GitHub revision](https://github.com/zenml-io/zenml-io-v2/blob/3123d772efa240d36182d08351255a626b9d8aa8/src/content/compare-kitaru/kitaru-vs-langgraph-deep-agents.mdx).

These examples mean this project cannot credibly claim to have coined “graph engineering,”
“graph-native harness,” or the general progression beyond harness engineering.

## Defensible positioning

The proposed project name—**Graph-Native Agent Control Plane**—appeared unused in the documented
exact searches. The project's more useful contribution is a precise, falsifiable formulation:

> Graph engineering advances harness engineering when agent-control decisions become explicit,
> typed, replayable graph transitions instead of remaining implicit in prompts, callbacks, and
> mutable orchestration code.

That formulation should be presented as this project's thesis and implementation focus, not as a
claim to have invented graph orchestration. Its credibility depends on the executable contracts,
tests, replay, and externally evaluated interventions that accompany it.
