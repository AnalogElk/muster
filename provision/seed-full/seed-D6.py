#!/usr/bin/env python3
"""
seed-D6.py - domain-content-client: KB shelves + demo-user org link.

Run on the muster-demo box:
    python3 ~/elk-os/provision/seed-full/seed-D6.py

Scope (D6 work package, 2026-07-16):
  1. kb_spaces: 3 employee spaces (design, operations, client-success) plus one
     client-visible space (working-with-muster). Upsert by slug.
  2. kb_pages: 5 published pages per new employee space, 6 pages in
     working-with-muster (min_role client). Upsert by slug (page slugs are
     GLOBALLY unique: the detail route is /api/portal/kb/pages/[slug]).
  3. contacts: demo@muster.dev contact (upsert by email) + organizations_contacts
     junction to org 2 (Cedar & Co Coffee). Lights the client-portal org-gated
     cards via the auth contacts fallback.

HARD GUARDS:
  - NEVER touches the Engineering space 1845cdcb-1e6b-4802-9009-4ed40e14d156
    or its pages. Asserts its page count is unchanged at the end.
  - Add-only: existing rows are skipped, never patched or deleted.
  - is_test_data: false wherever the field exists (contacts only here;
    kb_spaces/kb_pages have no such field).
  - No em dashes in any seeded content.
"""

import json
import os
import sys
import urllib.parse
import urllib.request

BASE = "https://cms.musterr.dev"
ENGINEERING_SPACE_ID = "1845cdcb-1e6b-4802-9009-4ed40e14d156"


def load_env(path=os.path.expanduser("~/elk-os/.env")):
    env = {}
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                env[k.strip()] = v.strip()
    return env


TOKEN = load_env()["DIRECTUS_ADMIN_TOKEN"]


def req(method, path, params=None, body=None):
    url = BASE + path
    if params:
        url += "?" + urllib.parse.urlencode(params)
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(url, data=data, method=method)
    r.add_header("Authorization", "Bearer " + TOKEN)
    r.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(r) as resp:
            return json.loads(resp.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        detail = e.read().decode()[:400]
        raise RuntimeError(f"{method} {path} -> HTTP {e.code}: {detail}") from e


def find_one(collection, filt, fields="id"):
    res = req(
        "GET",
        f"/items/{collection}",
        params={"filter": json.dumps(filt), "fields": fields, "limit": 1},
    )
    rows = res.get("data") or []
    return rows[0] if rows else None


# ---------------------------------------------------------------------------
# 1. kb_spaces
# ---------------------------------------------------------------------------

SPACES = [
    {
        "slug": "design",
        "name": "Design",
        "icon": "palette",
        "order": 2,
        "min_role": "employee",
        "is_client_visible": False,
        "description": "Design standards for client work: review process, file hygiene, accessibility, tokens, and how work moves from design into development.",
    },
    {
        "slug": "operations",
        "name": "Operations",
        "icon": "settings",
        "order": 3,
        "min_role": "employee",
        "is_client_visible": False,
        "description": "How the studio runs day to day: the weekly rhythm, kickoffs, tooling and vendor policy, coverage, and expenses.",
    },
    {
        "slug": "client-success",
        "name": "Client Success",
        "icon": "heart-handshake",
        "order": 4,
        "min_role": "employee",
        "is_client_visible": False,
        "description": "Playbooks for keeping clients informed, happy, and renewed: communication standards, QBRs, escalations, and feedback loops.",
    },
    {
        "slug": "working-with-muster",
        "name": "Working With Muster",
        "icon": "compass",
        "order": 5,
        "min_role": "client",
        "is_client_visible": True,
        "description": "A guide for clients: how onboarding works, how to read invoices and release notes, how to request changes, and what our support commitments are.",
    },
]

# ---------------------------------------------------------------------------
# 2. kb_pages (slug -> page). Page slugs are globally unique.
# ---------------------------------------------------------------------------

PAGES = [
    # ---- Design (5) ----
    {
        "space": "design",
        "slug": "design-review-checklist",
        "title": "Design Review Checklist",
        "order": 1,
        "min_role": "employee",
        "tags": ["design", "review", "process"],
        "summary": "What reviewers check before any design ships to a client: layout, states, accessibility, and token compliance.",
        "body": """Every design that leaves the studio goes through one structured review. The goal is not taste policing. It is catching the things that are expensive to fix after a client has seen them: missing states, broken hierarchy, and accessibility problems.

## Before you request review

Confirm the file covers the complete flow, not just the happy path. Empty states, loading states, error states, and long-content states all need frames. If a screen holds a list, show it with zero items, one item, and forty items.

## What the reviewer checks

- Type scale and spacing follow the project tokens, with no one-off values
- Interactive elements have hover, focus, and disabled states
- Color contrast meets WCAG 2.1 AA for text and essential UI
- Copy is real or realistic, never lorem ipsum in a client-facing file
- Components come from the shared library where one exists

## After review

Resolve every comment before handoff, either by changing the design or replying with the reason it stays. Unresolved threads block the handoff ticket. When the review closes, move the file to the Ready column and link it in the project channel.""",
    },
    {
        "space": "design",
        "slug": "figma-file-organization",
        "title": "Figma File Organization",
        "order": 2,
        "min_role": "employee",
        "tags": ["design", "figma", "conventions"],
        "summary": "Naming, page structure, and archive rules that keep client Figma files navigable for anyone on the team.",
        "body": """A client file should be legible to someone who has never opened it. Any designer on the team may need to pick up a project mid-flight, and a tidy file is the difference between an hour of orientation and a day of archaeology.

## Page structure

Each client file uses the same page order: Cover, Ready for Dev, In Progress, Explorations, Components, Archive. The cover page carries the project name, the current phase, and the lead designer. Nothing ships from Explorations; work is promoted into Ready for Dev only after review.

## Naming

Frames are named for what they are, not where they sit. Use "Checkout / Payment / Error - card declined" rather than "Frame 412". Component names follow the shared library convention: category, slash, variant.

## Archiving

When a direction dies, move it to Archive with a short note about why. Do not delete explorations during an active engagement. Clients ask to revisit rejected directions more often than you would expect, and the note saves the team from re-litigating the same decision.""",
    },
    {
        "space": "design",
        "slug": "accessibility-standards",
        "title": "Accessibility Standards",
        "order": 3,
        "min_role": "employee",
        "tags": ["design", "accessibility", "wcag"],
        "summary": "The WCAG 2.1 AA baseline every deliverable meets, and the checks that happen at design time rather than QA time.",
        "body": """Accessibility is part of the definition of done on every engagement, not an add-on line item. The baseline is WCAG 2.1 AA. This page covers the checks that belong at design time; the engineering checklist lives with each project repo.

## Contrast and color

Body text needs 4.5:1 contrast against its background, large text 3:1, and essential UI elements 3:1. Never use color alone to carry meaning: pair state colors with an icon, a label, or a weight change. Test palettes in a contrast checker before the first review, not after.

## Structure and focus

Design the focus order explicitly. Every interactive element needs a visible focus state that is at least as prominent as its hover state. Modal patterns must show where focus lands on open and where it returns on close.

## Content

Headings form an outline, not a styling system. Alt text is drafted at design time for meaningful images and marked decorative otherwise. Form fields always have visible labels; placeholder text is never the only label.

If a client pushes back on an accessibility requirement, escalate to the project lead rather than quietly dropping it. We document the exception and the client's sign-off in the project decision log.""",
    },
    {
        "space": "design",
        "slug": "design-tokens-guide",
        "title": "Design Tokens Guide",
        "order": 4,
        "min_role": "employee",
        "tags": ["design", "tokens", "systems"],
        "summary": "How token sets are structured per client, and the rule that no hardcoded color, spacing, or type value ships.",
        "body": """Every client project carries a token set: colors, spacing, type scale, radii, and shadows defined once and referenced everywhere. Tokens are what make a rebrand a day of work instead of a month.

## Structure

Tokens live in three layers. Primitive tokens hold raw values, like the full color ramp. Semantic tokens map primitives to meaning: brand primary, surface, text muted, semantic error. Component tokens, used sparingly, map semantics to specific parts like button background.

Designs reference semantic tokens, never primitives. If a design needs a value the semantic layer does not cover, that is a conversation about extending the system, not a license to hardcode.

## The hard rule

No hardcoded values in shipped work. No hex codes typed into a component, no 17 pixel padding, no one-off font size. Spacing sits on the 8 point grid. If a mockup requires breaking the grid, flag it in review; nine times out of ten the layout is fighting a structural problem the grid would have exposed.

## Handoff

The token file exports alongside the design as JSON. Engineering consumes it directly, so a token rename is a coordinated change: update the export, note it in the handoff ticket, and tag the implementing developer.""",
    },
    {
        "space": "design",
        "slug": "handoff-to-development",
        "title": "Design to Development Handoff",
        "order": 5,
        "min_role": "employee",
        "tags": ["design", "handoff", "process"],
        "summary": "The handoff package a developer should receive: annotated flows, states, tokens, and a walkthrough that survives questions.",
        "body": """A handoff is complete when a developer can build the feature without messaging the designer. That is the bar. Most handoff pain comes from shipping a picture of the happy path and calling it a spec.

## The package

Every handoff ticket links a Ready for Dev section that contains the full flow with every state, annotations for behavior that a static frame cannot show, the token export, and any motion specs. Interactions that depend on data shape, like truncation or pagination, carry notes with realistic content lengths.

## The walkthrough

For anything larger than a component tweak, the designer walks the developer through the flow live, fifteen minutes maximum. The developer's questions during this call are a free audit of the spec; if a question cannot be answered from the file, the file is incomplete and gets updated before build starts.

## During the build

Design questions during implementation go in the ticket thread, not DMs, so decisions are recorded. The designer reviews the staging build against the file before the work moves to client review. Small deviations that improve the result are fine and get folded back into the file, so the file always matches what shipped.""",
    },
    # ---- Operations (5) ----
    {
        "space": "operations",
        "slug": "weekly-ops-rhythm",
        "title": "Weekly Ops Rhythm",
        "order": 1,
        "min_role": "employee",
        "tags": ["operations", "cadence", "meetings"],
        "summary": "The standing weekly cycle: Monday planning, midweek focus, Friday review, and the reports that anchor each.",
        "body": """The studio runs on a weekly cycle. The cadence exists to keep coordination cheap: two short standing sessions a week, everything else asynchronous.

## Monday planning

Thirty minutes, whole team. Each project lead states what ships this week and flags anything blocked. Capacity conflicts get resolved here, in the room, not discovered on Thursday. The output is an updated sprint board that reflects reality.

## Midweek

No standing meetings on Tuesday through Thursday. Deep work happens here. Questions go to project channels; anything urgent enough to interrupt someone should be urgent enough to call them.

## Friday review

Thirty minutes. Shipped work gets demoed, even rough work. The demo habit keeps quality visible and keeps projects from going quiet for weeks. After demos, leads update client-facing project status so Monday's client updates write themselves.

## The numbers

Two reports anchor the rhythm: the delivery report on Friday afternoon showing shipped versus planned per project, and the pipeline report on Monday showing proposals out, deals in motion, and starts scheduled. Both live in the portal and both get skimmed, not presented.""",
    },
    {
        "space": "operations",
        "slug": "project-kickoff-checklist",
        "title": "Project Kickoff Checklist",
        "order": 2,
        "min_role": "employee",
        "tags": ["operations", "kickoff", "checklist"],
        "summary": "Everything that must exist before billable work starts: signed SOW, workspace, access, kickoff call, and a first invoice date.",
        "body": """No billable work starts until kickoff completes. The checklist is short deliberately; every item on it has burned us at least once when skipped.

## Before the kickoff call

- Signed SOW and deposit invoice issued
- Project workspace created: board, repo, design file, client channel
- Internal roles assigned: project lead, design lead, engineering lead
- Access collected from the client: hosting, DNS, analytics, CMS, brand assets

Access is the item that slips. Chase it before the call, because a project that starts without production access ends with a launch delay.

## The kickoff call

One hour with the client's decision makers present. Cover scope boundaries in plain language, the communication plan, who approves what, and the first three milestones with dates. Record the call. Decisions made here go into the project decision log the same day.

## After the call

Send the kickoff summary within 24 hours: scope, milestones, owners, and the first invoice date. Schedule the first client checkpoint. Open the first sprint on the board with the milestone one tasks sized and assigned. When all of that is done, the project status flips to active and the clock starts.""",
    },
    {
        "space": "operations",
        "slug": "vendor-and-tooling-policy",
        "title": "Vendor and Tooling Policy",
        "order": 3,
        "min_role": "employee",
        "tags": ["operations", "tools", "vendors", "spend"],
        "summary": "How new tools get adopted, who owns each subscription, and the quarterly review that kills unused spend.",
        "body": """Tool sprawl is a tax on every project. This policy keeps the stack small, owned, and reviewed.

## Adopting a tool

Anyone can propose a tool. The proposal is a short note: the problem, the tool, the monthly cost, and what it replaces. If it replaces nothing, that is a flag, not a veto. The ops lead approves anything under 50 dollars a month; anything above goes to the partners. Trials are fine without approval as long as they are cancelled or converted within the trial window.

## Ownership

Every subscription has exactly one owner. The owner holds the admin seat, manages seats for the team, and answers for the renewal. Tools are registered in the portal tools list with cost, billing cycle, renewal date, and the account email, so spend is visible in one place rather than scattered across inboxes.

## The quarterly cull

Once a quarter, ops walks the tools list. Anything with no active usage in the past quarter gets cancelled unless its owner defends it in writing. Seat counts get trued up at the same time. The cull typically recovers a few hundred dollars a month, which is the point: small leaks, fixed on a schedule.""",
    },
    {
        "space": "operations",
        "slug": "time-off-and-coverage",
        "title": "Time Off and Coverage",
        "order": 4,
        "min_role": "employee",
        "tags": ["operations", "pto", "coverage"],
        "summary": "How to book time off, the coverage note every project lead writes before leaving, and the no-contact rule while away.",
        "body": """Time off only works when coverage is explicit. The policy has two halves: booking the time, and making sure nothing you own goes dark while you are gone.

## Booking

Request time off in the calendar as early as you can, two weeks minimum for anything longer than two days. The ops lead confirms against project milestones; the only reason a request gets pushed back is a hard launch date inside the window, and in that case the conversation is about moving the launch or the time, never quietly cancelling the time.

## The coverage note

Before you leave, every project you lead gets a coverage note in its channel: current state, what lands while you are out, who covers what, and where the bodies are buried. Write it for the person covering, not for yourself. A good coverage note answers the questions people would otherwise DM you on a beach.

## While you are away

You are away. Do not check the channels, and the team does not contact you except for a genuine emergency, defined as production down or a client relationship at risk. Anything else waits. The studio has survived every vacation so far and it will survive yours.""",
    },
    {
        "space": "operations",
        "slug": "expense-and-receipt-policy",
        "title": "Expense and Receipt Policy",
        "order": 5,
        "min_role": "employee",
        "tags": ["operations", "expenses", "receipts", "finance"],
        "summary": "What gets expensed, how receipts are filed the same week, and how billable expenses flow through to client invoices.",
        "body": """Expenses are boring when handled weekly and painful when handled quarterly. The policy optimizes for boring.

## What qualifies

Software and subscriptions used for client work or studio operations, travel booked for client engagements, and project materials. Meals qualify during client travel and client meetings. When in doubt, ask before spending, not after; retroactive surprises are how policies grow teeth.

## Filing

File the expense the week it happens. Every expense row in the portal gets a receipt attached, the amount with tax, the category, and the project when the spend is project-specific. Recurring subscriptions are entered once with their billing cycle and renewal date; the renewal scan handles the reminders.

## Billable expenses

Expenses passed through to a client, like stock licenses, plugins, or approved travel, are marked billable and linked to the project at entry time. Billable expenses land on the next project invoice as line items with the receipt available on request. Never surprise a client with a pass-through they did not approve; the approval lives in the project channel before the spend happens.

## Review

The finance review at month end reconciles filed expenses against the card statements. Anything on a statement without a filed expense gets chased individually, which nobody enjoys, so file weekly.""",
    },
    # ---- Client Success (5) ----
    {
        "space": "client-success",
        "slug": "client-communication-standards",
        "title": "Client Communication Standards",
        "order": 1,
        "min_role": "employee",
        "tags": ["client-success", "communication"],
        "summary": "Response time commitments, the weekly update format, and the plain-language rule for anything a client reads.",
        "body": """Clients rarely churn over quality. They churn over silence. These standards exist so no client ever wonders what is happening with their project.

## Response times

Acknowledge every client message within one business day, even if the full answer takes longer. The acknowledgement says when they will hear back, and that commitment gets kept. Support requests follow the SLA tiers published in the client help center; everything else follows this one rule.

## The weekly update

Every active project sends a written update each week, no exceptions, including weeks with little progress. The format is fixed: what shipped, what is in motion, what is blocked and on whom, and what happens next week. Blocked-on-client items get named explicitly with what we need and by when. A project that sends honest weekly updates never has a hard status meeting.

## Plain language

Anything a client reads gets written in plain language. No internal jargon, no framework names without context, no hedging. If a deadline is at risk, say it is at risk and say why and what we are doing about it. Clients forgive slips they saw coming; they do not forgive slips that were hidden in optimistic updates.""",
    },
    {
        "space": "client-success",
        "slug": "quarterly-business-reviews",
        "title": "Quarterly Business Reviews",
        "order": 2,
        "min_role": "employee",
        "tags": ["client-success", "qbr", "retention"],
        "summary": "The QBR structure for retainer clients: results against goals, what is next, and the honest health conversation.",
        "body": """Every retainer client gets a quarterly business review. The QBR is not a status meeting; the weekly updates handle status. It is the meeting where we prove the engagement is worth renewing.

## Preparation

Build the deck from the portal data: work shipped this quarter, outcomes against the goals set last quarter, site and product metrics where we have them, and spend against budget. Numbers first, narrative second. If the quarter was weak, the deck says so plainly and leads with the recovery plan, because the client already knows.

## The meeting

Sixty minutes with the client's stakeholders. Twenty minutes on results, twenty on what is next and what we recommend, twenty for the conversation that actually matters: what is working for them, what is not, and what is changing in their business that we should know about. The recommendations section is where growth comes from; bring one or two concrete proposals with rough sizing, not a menu.

## Afterward

Send the summary within two days: decisions, commitments on both sides, and the goals for next quarter. Log renewal risk honestly in the CRM after every QBR. A surprise non-renewal is a process failure, not bad luck.""",
    },
    {
        "space": "client-success",
        "slug": "escalation-playbook",
        "title": "Escalation Playbook",
        "order": 3,
        "min_role": "employee",
        "tags": ["client-success", "escalation", "incidents"],
        "summary": "What counts as an escalation, who owns it, the first-hour moves, and how the loop closes with the client.",
        "body": """An escalation is any situation where a client relationship is at risk: a missed commitment, a production incident on their property, a quality complaint, or a tone shift in their communication that a project lead cannot resolve alone.

## Triggering

Anyone can escalate. Post in the escalations channel with the client, the situation in two sentences, and what has already been said to the client. Escalating early is free; escalating late is expensive. Nobody has ever been criticized here for raising a flag that turned out to be minor.

## The first hour

The account owner takes point and does three things: acknowledges to the client that we see the problem and own it, gets the facts straight internally before promising anything specific, and sets the next communication time with the client. That first message contains no excuses and no blame, including blame of vendors or their own team.

## Resolution and the loop

Fix the problem, then close the loop with a short written postmortem for the client: what happened, why, what we changed so it does not repeat. Internally, log the escalation in the CRM against the account and add the durable lesson to the knowledge base. Two escalations from the same root cause means the fix was cosmetic; treat the second one as a process incident.""",
    },
    {
        "space": "client-success",
        "slug": "renewals-and-upsells",
        "title": "Renewals and Upsells",
        "order": 4,
        "min_role": "employee",
        "tags": ["client-success", "renewals", "growth"],
        "summary": "The renewal timeline that starts 90 days out, and how expansion proposals grow from logged client needs.",
        "body": """Renewals are won during the engagement, not during the renewal conversation. By the time the contract end date is close, the outcome is mostly decided. The process here makes sure we are never negotiating from surprise.

## The 90 day timeline

Ninety days before a contract ends, the account shows up in the renewal pipeline. The account owner reviews the health signals: QBR notes, escalation history, invoice payment behavior, and engagement in the weekly updates. At 60 days, the renewal conversation opens explicitly with the client, framed around next-quarter goals rather than paperwork. At 30 days, terms are agreed or the disengagement plan starts. A renewal that reaches 15 days unresolved gets partner attention.

## Expansion

Upsell proposals come from logged needs, not from quota pressure. Every time a client mentions a problem outside current scope, it goes into the CRM as an opportunity note. When two or three notes cluster around a theme, that is a proposal. Bring it at the QBR with rough sizing. Expansion built this way converts well because the client watched us notice their problem before we tried to sell them the solution.

## Disengagement

When a client does not renew, exit well: clean handoff documentation, credentials returned, a final invoice with no surprises. Former clients who exited well come back and refer others. Burned exits echo for years.""",
    },
    {
        "space": "client-success",
        "slug": "csat-and-feedback-loop",
        "title": "CSAT and the Feedback Loop",
        "order": 5,
        "min_role": "employee",
        "tags": ["client-success", "feedback", "csat"],
        "summary": "The two feedback instruments we run, and the rule that every piece of feedback gets a visible response.",
        "body": """We measure client satisfaction with two lightweight instruments, and we treat the responses as work items rather than dashboard decoration.

## The instruments

After every milestone delivery, the client gets a two-question pulse: how did this delivery go, one to five, and what should we do differently. After every engagement or quarter, the fuller survey adds a would-you-refer-us question and free text. Both are short on purpose. Long surveys measure who has time for surveys.

## The loop

Every response gets acknowledged within two business days, personally, by the account owner. A four or five gets a thank you. A three or below gets a conversation, not a form reply: what happened, what would have made it a five. The score is the smoke alarm; the conversation is where the information lives.

## What the numbers feed

Scores and themes roll up quarterly. A recurring theme across clients becomes a process change with an owner and a deadline, logged where the team can see it. When a change traces back to client feedback, we tell the clients who raised it. Closing the loop out loud is what convinces clients the surveys are worth answering, which keeps the response rate high enough to matter.""",
    },
    # ---- Working With Muster (client-visible, 6) ----
    {
        "space": "working-with-muster",
        "slug": "welcome-and-onboarding",
        "title": "Welcome and Onboarding",
        "order": 1,
        "min_role": "client",
        "tags": ["onboarding", "getting-started"],
        "summary": "What happens in your first two weeks: kickoff, access setup, your portal account, and who to contact for what.",
        "body": """Welcome. This page walks you through your first two weeks with us and how the engagement runs after that.

## Your first two weeks

Week one starts with the kickoff call. We will confirm scope, milestones, and who on your side approves what. Ahead of that call we will ask for access to the systems the project touches, things like hosting, DNS, analytics, and your CMS. Getting access sorted early is the single biggest thing you can do to keep the schedule intact.

Week two is when work becomes visible. Your project board fills in, the first tasks move, and you receive your first weekly update.

## Your portal

This portal is your window into the engagement. The dashboard shows project status, recent activity, and links to everything important. Invoices, project tasks, releases, and support all live here. You will receive a weekly written update in addition to the portal, so you never need to log in just to find out whether things are moving.

## Who to contact

Your project lead is your first call for anything about the work itself. For billing questions, reply to any invoice email or raise a support request in the portal. For anything urgent, the support page lists our response commitments. When in doubt, ask your project lead; routing you correctly is our job, not yours.""",
    },
    {
        "space": "working-with-muster",
        "slug": "how-to-read-your-invoice",
        "title": "How to Read Your Invoice",
        "order": 2,
        "min_role": "client",
        "tags": ["billing", "invoices"],
        "summary": "A walkthrough of each invoice section: line items, billing types, pass-through expenses, payment terms, and due dates.",
        "body": """Our invoices are designed to be readable without a call to your accountant. This page explains each part.

## The header

The top of every invoice shows the invoice number, the issue date, the due date, and the project it belongs to. Invoice numbers are sequential and unique, so referencing one in an email is always unambiguous.

## Line items

Each line names the work or item, the quantity or period, and the amount. Fixed-fee milestones appear as a single line per milestone. Retainer periods appear as one line per period. Where your agreement includes pass-through expenses, such as stock licenses or approved travel, they appear as their own lines marked as expenses, and receipts are available on request.

## Billing types

Depending on your agreement you will see one of a few patterns: one-time invoices for fixed scopes, recurring invoices for retainers and subscriptions, fixed-term invoices that run for an agreed number of months, or pay-over-time schedules that split a large scope into instalments. The pattern is stated on the invoice so you always know whether another one is coming.

## Payment

Payment terms and the due date are printed near the total. If an invoice is going to be a problem, tell us before the due date; a heads-up costs nothing and keeps the schedule conversation separate from the payment conversation. Questions about any line are welcome, and the fastest route is replying to the invoice email itself.""",
    },
    {
        "space": "working-with-muster",
        "slug": "requesting-changes",
        "title": "Requesting Changes",
        "order": 3,
        "min_role": "client",
        "tags": ["process", "change-requests", "scope"],
        "summary": "How to raise a change request, what happens to it, and how changes inside and outside scope are handled.",
        "body": """Projects evolve, and a good change process keeps evolution from turning into confusion. Here is how to ask for changes and what happens next.

## How to raise one

Send change requests through your project channel or as a support request in the portal, in whatever words come naturally. You do not need to classify anything. Describe what you want to be different and, if you can, why; the why often lets us propose something better than the literal ask.

## What happens next

Your project lead reviews every request within two business days and comes back with one of three answers. Small changes that fit inside the current scope get scheduled straight onto the board and you will see them in the weekly update. Changes that affect scope, budget, or timeline come back as a short written estimate with the impact spelled out, and nothing proceeds until you approve it in writing. Requests we think are a mistake get an honest counter-proposal rather than silent compliance; you are paying us to have opinions.

## The one rule

All changes go through the process, even ones agreed verbally on a call. If we agreed to something on a call, you will see it written in the project channel within a day. If you do not see it written down, it is not yet real, and you should nudge us. This rule protects both sides: no forgotten promises, and no invoice surprises.""",
    },
    {
        "space": "working-with-muster",
        "slug": "support-slas",
        "title": "Support SLAs",
        "order": 4,
        "min_role": "client",
        "tags": ["support", "sla"],
        "summary": "Our support tiers, response and resolution commitments, and what to do when something is genuinely urgent.",
        "body": """This page states our support commitments plainly so you never have to guess how fast to expect a response.

## Severity tiers

Critical means your production site or product is down or unusable for your customers. High means a core function is broken but the property is up, or a launch-blocking problem has appeared. Normal covers bugs, questions, and small fixes that do not block your business. Low covers cosmetic issues and nice-to-haves.

## Our commitments

Critical issues are acknowledged within 2 business hours and worked continuously until resolved, with updates at least every 4 hours. High issues are acknowledged within 4 business hours with a plan inside one business day. Normal requests are acknowledged within one business day and scheduled into the current or next sprint. Low items are acknowledged within two business days and batched sensibly.

Business hours are Monday to Friday, 9:00 to 17:00 Pacific, excluding US holidays. Retainer agreements with extended coverage state their hours in the agreement and those terms win where they differ.

## Raising an issue

Use the support section of this portal so your request is tracked from the start; email reaches us too, but the portal guarantees nothing falls between inboxes. For critical issues, raise the request and then also call or message your project lead directly. Say clearly that production is down; those words move people.""",
    },
    {
        "space": "working-with-muster",
        "slug": "release-notes-guide",
        "title": "How to Read Release Notes",
        "order": 5,
        "min_role": "client",
        "tags": ["releases", "changelog"],
        "summary": "What our release notes contain, how versions are numbered, and how to connect a release to the work you approved.",
        "body": """Every time we ship a meaningful batch of work to your property, we publish a release in this portal. Release notes are how you can see, at any time, exactly what has shipped and when.

## What a release contains

Each release has a version number, a date, and a changelog grouped into plain sections: Added for new features, Changed for modifications to existing behavior, Fixed for bug fixes, and Security for anything protective. Where a change alters something your team uses day to day, the notes call it out explicitly with what to expect.

## Version numbers

Versions follow the widely used three-part pattern, such as 2.4.1. The first number changes for major overhauls, the middle number for new features, and the last for fixes. You do not need to memorize this; the practical takeaway is that a bigger jump means a bigger change, and the changelog always tells the full story.

## Connecting releases to your requests

Release entries reference the work behind them, so a change you requested can be traced from your original request, through the weekly updates, to the release where it shipped. If you ever cannot find where something landed, ask your project lead and they will point at the exact release.

We keep the full release history available for the life of the engagement, so an audit of what changed and when is always one page away.""",
    },
    {
        "space": "working-with-muster",
        "slug": "your-portal-at-a-glance",
        "title": "Your Portal at a Glance",
        "order": 6,
        "min_role": "client",
        "tags": ["portal", "guide", "getting-started"],
        "summary": "A quick tour of each portal section: dashboard, projects, tasks, invoices, releases, support, and the knowledge base.",
        "body": """This is a one-page tour of everything in your portal and what each section is for.

## The dashboard

The dashboard is the summary view: your active projects and their status, recent activity, important links for your properties, and anything that needs your attention such as an approval or an unpaid invoice. If you only ever open one page, this is the one.

## Projects and tasks

The projects section shows each engagement with its milestones, progress, and team. Drill into a project for its full task board, the same board our team works from, so you see real state rather than a curated summary. The tasks section collects everything across projects that is waiting on your review or approval.

## Invoices and billing

All invoices live in the invoices section with their status: paid, due, or overdue. You can open any invoice for its full line-item detail. See the guide on reading your invoice for a walkthrough of each part.

## Releases, support, and the knowledge base

Releases list everything that has shipped, newest first. Support is where you raise requests and track their progress against our published SLAs. And this knowledge base holds guides like this one, covering how we work together. Everything here stays available for the life of the engagement, so you can always find the answer without waiting on a reply.""",
    },
]

# ---------------------------------------------------------------------------
# 3. Demo contact + org junction
# ---------------------------------------------------------------------------

DEMO_CONTACT = {
    "email": "demo@muster.dev",
    "first_name": "Muster",
    "last_name": "Demo",
    "status": "active",
    "job_title": "Demo Viewer",
    "is_test_data": False,
}
DEMO_ORG_ID = 2  # Cedar & Co Coffee. Deliberately NOT org 1 (StationKioskCard).


def main():
    # Pre-flight: record Engineering page count so we can prove it unchanged.
    eng_before = req(
        "GET",
        "/items/kb_pages",
        params={
            "filter": json.dumps({"space": {"_eq": ENGINEERING_SPACE_ID}}),
            "aggregate[count]": "id",
        },
    )["data"][0]["count"]["id"]

    # ---- kb_spaces ----
    created = updated = skipped = 0
    space_ids = {}
    for sp in SPACES:
        existing = find_one("kb_spaces", {"slug": {"_eq": sp["slug"]}})
        if existing:
            space_ids[sp["slug"]] = existing["id"]
            skipped += 1
            continue
        body = dict(sp)
        body["status"] = "published"
        res = req("POST", "/items/kb_spaces", body=body)
        space_ids[sp["slug"]] = res["data"]["id"]
        created += 1
    print(f"kb_spaces: created {created} / updated {updated} / skipped {skipped}")

    # ---- kb_pages ----
    created = updated = skipped = 0
    for pg in PAGES:
        for k in ("title", "summary", "body"):
            if "\u2014" in pg[k] or "\u2013" in pg[k]:
                raise RuntimeError(f"em/en dash found in page {k}: {pg['slug']}")
        existing = find_one("kb_pages", {"slug": {"_eq": pg["slug"]}})
        if existing:
            skipped += 1
            continue
        body = {
            "status": "published",
            "order": pg["order"],
            "title": pg["title"],
            "slug": pg["slug"],
            "summary": pg["summary"],
            "body": pg["body"],
            "min_role": pg["min_role"],
            "tags": pg["tags"],
            "space": space_ids[pg["space"]],
        }
        req("POST", "/items/kb_pages", body=body)
        created += 1
    print(f"kb_pages: created {created} / updated {updated} / skipped {skipped}")

    # ---- demo contact ----
    created = skipped = 0
    existing = find_one("contacts", {"email": {"_eq": DEMO_CONTACT["email"]}})
    if existing:
        contact_id = existing["id"]
        skipped += 1
    else:
        res = req("POST", "/items/contacts", body=DEMO_CONTACT)
        contact_id = res["data"]["id"]
        created += 1
    print(f"contacts: created {created} / updated 0 / skipped {skipped} (demo contact id {contact_id})")

    # ---- organizations_contacts junction ----
    created = skipped = 0
    existing = find_one(
        "organizations_contacts",
        {
            "_and": [
                {"organizations_id": {"_eq": DEMO_ORG_ID}},
                {"contacts_id": {"_eq": contact_id}},
            ]
        },
    )
    if existing:
        skipped += 1
    else:
        req(
            "POST",
            "/items/organizations_contacts",
            body={"organizations_id": DEMO_ORG_ID, "contacts_id": contact_id},
        )
        created += 1
    print(f"organizations_contacts: created {created} / updated 0 / skipped {skipped}")

    # Post-flight: Engineering space untouched.
    eng_after = req(
        "GET",
        "/items/kb_pages",
        params={
            "filter": json.dumps({"space": {"_eq": ENGINEERING_SPACE_ID}}),
            "aggregate[count]": "id",
        },
    )["data"][0]["count"]["id"]
    if int(eng_before) != int(eng_after):
        raise RuntimeError(
            f"ENGINEERING SPACE PAGE COUNT CHANGED: before {eng_before} after {eng_after}"
        )
    print(f"engineering-space guard: {eng_after} pages before and after (untouched)")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"FAILED: {exc}", file=sys.stderr)
        sys.exit(1)
