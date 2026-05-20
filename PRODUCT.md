# OccuEVRoute Product Context

## Register
product

## Product Purpose
OccuEVRoute is a course-demo EV charging route planning tool. It helps a presenter show how a selected Shenzhen location, vehicle constraints, route-search settings, and algorithm choice produce ranked charging-station recommendations and route diagnostics.

## Users
- Course presenters explaining the recommendation workflow during a demo or defense.
- Reviewers who need to understand the route result, feasibility constraints, and algorithm behavior without reading the code.

## Design Principles
- Keep the map as the primary workspace.
- Reveal the planning flow in a clear order: choose location, tune search and vehicle inputs, recommend stations, inspect route and diagnostics.
- Keep advanced algorithm and diagnostic controls available but collapsed by default.
- Use restrained product UI styling. Color should communicate state, selection, route layers, and errors rather than decoration.

## Anti-Goals
- Do not make this feel like a marketing landing page.
- Do not hide the algorithm explanation entirely; it is part of the course-demo value.
- Do not introduce a large UI framework for this restructuring.
