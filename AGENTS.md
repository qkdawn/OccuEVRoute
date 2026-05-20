# OccuEVRoute Agent Instructions

These instructions define the project-level system prompt for AI coding agents working in this repository.

## Product Context

OccuEVRoute is a course-demo EV charging route planning tool for Shenzhen. It combines road-network search, battery feasibility, charger availability, route diagnostics, and nearby POI context to recommend charging stations.

Keep the experience focused on the map and the planning workflow. The product should help presenters and reviewers understand how inputs, constraints, algorithms, and diagnostics produce the final station ranking.

## Software Design Philosophy

Use John Ousterhout's *A Philosophy of Software Design* as the default design lens. The goal of software design is to reduce complexity for future readers and changers, not merely to make the current patch work.

- Prefer deep modules: simple, stable interfaces hiding substantial implementation detail. Do not split code into many shallow functions or classes merely to make individual units shorter.
- Hide information aggressively. Keep data-shape decisions, algorithm choices, caching, fallback behavior, validation details, and error recovery inside the module that owns them.
- Pull complexity downward. When a lower-level module can reasonably infer, normalize, validate, default, cache, retry, or recover, handle that inside the lower-level module instead of forcing every caller to know the rule.
- Keep different layers at different abstractions. A new layer must add meaningful semantics, policy, orchestration, or simplification. Avoid pass-through methods, pass-through parameters, and wrappers that only rename the next call.
- Define errors out of existence when possible. Prefer APIs and data models that make invalid states unrepresentable or automatically handled. Use explicit errors only when the caller can make a meaningful decision.
- Optimize for the reader and future maintainer. If a change increases cognitive load, dependencies, hidden coupling, or unclear ownership, treat that as a design smell even if the code works.
- Invest strategically while implementing. When touching a module, leave its interface clearer, its responsibility sharper, or its error surface smaller, without doing unrelated rewrites.

## Repository Ownership Boundaries

- `backend/` owns product-level API behavior, request validation, response shaping, and translation between HTTP clients and domain modules.
- `src/route_planning/` owns graph search, station feasibility, candidate selection, snapping, scoring, route diagnostics, and algorithm-specific details.
- `src/waiting_prediction/` owns model training, feature construction, evaluation, and prediction semantics.
- `src/data_processing/` owns raw-data ingestion, cleaning, generated artifacts, and reproducible preprocessing steps.
- `frontend/` owns interaction, map visualization, UI state, and user-facing workflow. It should not duplicate backend feasibility, graph, or model rules.
- `docs/` owns project explanation, reports, figures, and model notes.

When a rule appears in more than one layer, prefer moving it downward into the owning domain module and exposing a simpler result upward.

## Engineering Judgment

When choosing an implementation, ask:

1. Does this reduce the amount of information future developers must keep in their heads?
2. Is complexity placed in the module that has the most context to handle it?
3. Does this interface expose policy or implementation details that could be hidden?
4. Is this abstraction deep enough to justify its existence?
5. Are errors being prevented by design, or merely pushed upward for callers to handle repeatedly?

Prefer the repository's existing patterns, frameworks, and helper APIs over inventing new infrastructure. Keep edits scoped to the modules implied by the request. Add abstractions only when they remove real complexity, reduce meaningful duplication, or match an established local pattern.

## Error Handling

Design APIs so callers receive useful domain results instead of needing to reconstruct internal failure modes.

- Normalize and validate user inputs at the boundary closest to their source.
- Keep route-search and data-loading edge cases inside the owning domain modules whenever possible.
- Return explicit rejection reasons or diagnostics only when they are part of the product behavior.
- Avoid repeated `try`/`except`, null checks, fallback constants, and validation branches across callers.
- Prefer typed schemas and constrained values over loosely shaped dictionaries.

## Frontend Principles

- Keep the map as the primary workspace.
- Reveal the planning flow in a clear order: choose location, tune search and vehicle inputs, recommend stations, inspect route and diagnostics.
- Keep advanced algorithm and diagnostic controls available but collapsed by default.
- Use restrained product UI styling. Color should communicate state, selection, route layers, and errors rather than decoration.
- Do not make the app feel like a marketing landing page.
- Do not hide algorithm explanation entirely; it is part of the course-demo value.
- Do not introduce a large UI framework unless the existing implementation clearly cannot support the required workflow.

## APOSD Red Flags

Before finishing a code change, scan for these design smells:

- Shallow wrappers that only forward calls.
- Parameters passed through multiple layers without being used.
- Configuration options that callers must tune but the module could infer.
- Repeated validation, fallback, or error handling across callers.
- Layers that share the same abstraction or vocabulary.
- Comments explaining awkward code that should instead become a clearer abstraction.
- Public interfaces exposing data formats, model internals, route-search details, cache details, or library quirks unnecessarily.

## Verification

Let test coverage scale with risk and blast radius. For narrow changes, run the smallest relevant checks. For shared behavior, route planning, API contracts, or frontend workflows, broaden verification to include unit tests, API checks, or browser inspection as appropriate.

When changing frontend behavior, verify that text fits, controls are usable, and map-related state remains coherent across realistic viewport sizes.

## Git Commit Style

Use Conventional Commits for all repository commits:

- `feat(scope): ...` for user-visible functionality.
- `fix(scope): ...` for bug fixes.
- `style(scope): ...` for UI/CSS-only changes that do not alter behavior.
- `refactor(scope): ...` for code restructuring without behavior changes.
- `docs(scope): ...` for documentation-only changes.
- `test(scope): ...` for tests.
- `chore(scope): ...` for tooling, build, dependency, or maintenance changes.

Keep the subject short, imperative, and lowercase after the type. Prefer scopes such as `frontend`, `backend`, `routing`, `data`, `models`, or `docs`.
