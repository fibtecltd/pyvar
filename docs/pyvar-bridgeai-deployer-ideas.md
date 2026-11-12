# pyvar: BridgeAI deployer ideas

**Draft, 12 November 2026.** Who could be the deployer in a BridgeAI Deployment Catalyst (AI for Decision Critical Systems) application for pyvar, and how to test a candidate quickly. The eligibility rules come from the competition's pages and briefing slides (UKRI, Innovate UK Business Connect and the competition page, read 12 November). **The names below are ideas from general knowledge. They have not been checked for size, sector, eligibility or interest, and none has been approached.** Read it with `docs/pyvar-funding-fit-swot.md`, which explains why BridgeAI is conditional for pyvar.

## First, the fit question

The deployer only matters if Innovate UK accepts that pyvar's AI component belongs in this strand. The component is the portal assistant (a measured answer bank written by Claude models and gated by graders and a second model, plus a typed agent path behind a flag that is off). It helps people understand and use risk functions; it does not make risk decisions. Send the strand-fit question to BridgeAI@iuk.ukri.org **by 24 November** (10 working days before closing), asking whether this fits Decision Critical Systems, another strand, or neither. Applying to the wrong strand makes the application ineligible. Without a yes, a deployer search is wasted effort.

## Why the deployer decides the application

The competition has ten scored questions, each marked 1 to 10 (assessor guidance; no weights or pass mark are published). At least four lean directly on the deployer:

| Scored question | What it needs from the deployer, in pyvar's case |
| --- | --- |
| Real-world application and benefit | Quantified annual savings at a single site, for example analyst hours spent finding the right function, preparing inputs or checking results, and errors avoided |
| Deployer readiness | The risk team's environment: people, data (synthetic first), systems and workflows available for the demonstration |
| Route to deployment | Model-risk governance, data protection and assurance requirements for an AI-assisted tool in a regulated firm |
| Learning | Evidence and data collected in the deployer's setting: time saved, error rates, trust |

The deployer also appears as an unscored question (the organisation acting as AI Deployer), and the sector of the deployment context must be named.

## What a deployer must be

From the competition pages and slides:

- A UK-registered **medium or large business**, or a **UK-based public sector organisation**. Check size against the gov.uk company accounts guidance the competition links to; micro and small businesses are not eligible as deployers.
- Operating in one of seven sectors: health and life sciences; **financial services**; advanced manufacturing; clean energy industries; defence; professional and business services; creative industries.
- Providing a **meaningful operational setting**, and access to the users, data, workflows, systems or processes the project needs.
- Accounting for **30% to 50% of the project's total eligible costs**. The grant covers up to 60% of a medium organisation's costs and 50% of a large one's, so the deployer bears the rest.
- Working with the lead to develop the use case and assess readiness; willing to take part in later phases if invited. If the deployer drops out, a replacement must be found.
- The lead's product must not already be commercially deployed in the proposed use case, so the use case should be new at this deployer.
- A deployer can appear in up to three applications across the three strands, each materially different.

## Ideas, by type

All of these are financial services, a listed sector. Most named firms are large, which means slow to commit; a mid-sized firm may decide faster.

| Type | Examples (unverified) | Why it might fit | What to check |
| --- | --- | --- | --- |
| Building societies and mid-sized banks that run their own liquidity, interest-rate and capital analysis | Skipton, Coventry, Leeds and Yorkshire building societies; Shawbrook, Paragon, Close Brothers, OakNorth | pyvar has liquidity ratio, ALM and interest-rate-risk functions; smaller treasury and risk teams may lack costly vendor tools | Size; who owns the risk tooling decision; model-risk governance for an AI-assisted tool |
| Asset managers | Schroders, Jupiter, Ninety One, M&G | Market-risk and portfolio analytics functions | Whether their risk analysis is outsourced; data restrictions |
| Digital banks and lenders | Zopa, Starling, Atom bank | Engineering-led teams that may adopt an API quickly | Whether they build risk tooling in-house |
| UK public bodies in financial services | British Business Bank, UK Export Finance, National Wealth Fund | Eligible as public sector; credit and ALM analysis | Procurement and governance speed |

**Warm routes beat cold ones in 26 days.** Ask the adviser for three introductions to UK medium or large financial-services firms with a risk team; ask the owner's own network; and ask any user of the plugins or the API whether their employer could host a deployment (no named user is recorded).

## Screening a candidate in one call

Ask, and write down the answers:

1. Is the organisation UK-registered, and is it medium or large (headcount and turnover)? Or a UK public body?
2. Which of the seven sectors does it operate in?
3. How does its risk team find and apply analytical methods today, how many analysts, how much time, and which tools?
4. Who would be the project lead on its side, and who could give access to its environment and workflow?
5. Could it carry 30% to 50% of the project's eligible costs (staff time counts as eligible cost; confirm), and bear 40% to 50% of its own share after the grant?
6. What governance would an AI-assisted tool need to pass (model-risk management, data protection, outsourcing)?
7. Could it write a letter of support, and name a contact for the application by a date that leaves a week to write?
8. Is any similar tool already deployed there?
9. Would it join later phases if invited, including co-investment in Phase 2 and Phase 3?

## What to offer and what not to claim

Offer: a funded evaluation of an AI guide and agent over validated risk functions in its own team; a design in which the model never sees portfolio data or computed results; measured accuracy and cost from an existing evaluation harness; human oversight.

Do not claim that pyvar is regulatory-grade or independently validated: the README says it is not independently validated for regulatory use. Do not claim that the assistant beats static documentation: that comparison has not been measured. A project could make both measurements part of the work.

## Timeline for deciding

| Date (2026) | Step |
| --- | --- |
| 13 to 16 Nov | First calls to candidates; ask the adviser for introductions |
| 17 Nov | Innovate UK support advises contact at least 15 working days before closing |
| 18 Nov | Go/no-go, a suggested date: is there a deployer willing to commit, and does the strand fit look plausible? |
| 24 Nov | Last day to email BridgeAI@iuk.ukri.org about strand fit |
| About 27 Nov | A suggested date for a written commitment and a named contact from the deployer, to leave a week to write |
| 8 Dec, 11:00 UK | Competition closes |

If there is no committed deployer and no yes on strand fit by then, do not submit a thin application.

## Tracking

| Candidate | Type | UK-registered and size | Sector | Contact (outside the repo) | Status | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| | | | | | | |
| | | | | | | |
| | | | | | | |
| | | | | | | |
| | | | | | | |
