# Help System Overhaul: Three Prompts to Fix Four Months of Documentation Drift

- URL: https://ef-map.com/blog/ai-natural-language-commands-workers-ai
- Published: 2026-01-28
- Category: Development Methodology
- Description: How we overhauled EF-Map's outdated Help system in under 30 minutes of operator time using LLM sub-agents - fixing 20+ outdated entries, adding search, and cleaning up the UI.

EF-Map's Help panel was a mess. Twenty-plus entries describing features as they existed months ago. Missing documentation for major additions. UI problems making it hard to find anything. And the classic solo dev excuse: "I'll update it later."

Here's how three LLM prompts and about 30 minutes of my time fixed all of it - and why sub-agents made it possible.

## How Help Documentation Drifted

The Help system started strong. Back in August 2025, I had a simple workflow: ship a feature, immediately write the Help entry. Each feature got documented while the implementation was fresh in my mind.

Then I stopped.

Not consciously. Just laziness, forgetfulness, the growing backlog of features that felt more exciting than documentation. One skipped entry became two. Two became ten. Over four months, the gap widened:

- Features evolved but their Help text didn't. The SSU Finder description still referenced the old UI. Smart Gates mentioned outdated workflow steps.

- New features shipped undocumented. Log Parser, Awakened Cinema, Performance Mode - all added with no Help entries at all.

- Old entries contained dead references. Features that moved panels, changed names, or gained new options.

The fundamental problem is solo dev reality: you won't remember exact details of a feature shipped 2-3 months ago. The codebase remembers. The Help panel doesn't update itself.

## The UI Problems

Beyond stale content, the Help panel had structural issues:

#### Before: What Was Wrong

- Too much orange - Trying to use orange for emphasis, but it competed with actual CTAs (calls-to-action)

- No search - 25+ collapsible items with no way to find what you need

- Key links buried - Technical Blog, Patch Notes, Support, and Embed Guide hidden at the bottom, below 20 feature descriptions

- Scroll jumps - Expanding an item mid-scroll caused the page to jump as content pushed everything down

Users opening Help to find Patch Notes (or the Technical Blog, Support section, or Embed Guide) had to scroll past every feature description. Users searching for a specific feature had to manually expand each section.

## The "Insurmountable Task" Illusion

For months, updating Help felt like an insurmountable project. Audit every feature. Compare to current implementation. Rewrite 20+ entries. Test each one. Fix the UI. Add search.

This mental framing was the real blocker. The actual work?

- 2 prompts for the overhaul (content audit + UI fixes)

- 1 prompt for this blog post

- Operator time: approximately 5-8 minutes speaking, approximately 20-30 minutes agent runtime per prompt

Total cost: approximately $0.36 across three prompts at roughly $0.12 each.

The task that felt like a weekend project took less time than writing this blog post by hand would have.

## Why Sub-Agents Were Key

This overhaul would have choked a single LLM agent. Here's why:

GitHub Copilot agent mode has limits: roughly 128k tokens input, 16k tokens output per context window. When you're updating 25+ Help entries - reading source files to verify current behavior, rewriting descriptions, checking for accuracy - you hit context compaction fast. The model starts "forgetting" earlier parts of the conversation.

Sub-agents solve this by getting their own context windows:

- Orchestrator agent stays focused on the overall plan

- Sub-agent 1 audits Routing features (P2P, Explore Mode, Scout Optimizer)

- Sub-agent 2 audits Display features (region stats, star labels, performance mode)

- Sub-agent 3 audits Tool features (Log Parser, Blueprints, SSU Finder)

- Each sub-agent returns a summary, the orchestrator combines them

Without sub-agents, I'd have needed to split the work across multiple chat sessions manually - tracking what was done, what needed review, avoiding duplicate work. The agent handles that coordination automatically.

A single prompt costs around $0.12. Three prompts to completely overhaul a neglected system: $0.36. The alternative was either continuing to ignore it or spending hours doing the audit manually - and realistically, I would have kept ignoring it.

LLMs don't just make development faster. They make "boring but important" maintenance tasks actually get done because the cost/effort barrier drops below the threshold of procrastination.

## What Changed: Before and After

### Content Updates

Examples of entries that needed correction:

- SSU Finder - Updated to reflect grid view, fuel estimate columns, and freemium subscription tier

- Smart Gates - Rewrote to explain current bidirectional routing and authorization visualization

- Region Statistics - Added kill activity heatmaps and top killers section that shipped in December

- Performance Mode - New entry explaining GPU auto-detection and what it disables

- Log Parser - New entry covering local analytics, mining stats, and privacy-first approach

### UI Improvements

The structural changes make the Help panel actually useful:

- Quick Links section at the top - Technical Blog, Patch Notes, Support This Project, Embed Guide immediately visible

- Search box filters entries in real-time as you type

- Muted category styling replaces the orange-everywhere approach

- Scroll lock when expanding items prevents jarring jumps

## The Three-Prompt Process

### Prompt 1: Content Audit (about 25 min agent time)

Goal: Review every Help entry against current codebase. Flag outdated content. Identify missing features. Propose rewrites.

The agent used sub-agents to parallelize the audit across feature categories. Each sub-agent read relevant source files (SmartAssembliesPanel.tsx, LogParserPanel.tsx, etc.) and compared against Help text.

Output: A structured report with current/outdated status per entry, plus draft rewrites.

### Prompt 2: Implementation + UI Fixes (about 20 min agent time)

Goal: Apply all content updates. Add search functionality. Reorganize layout. Fix scroll behavior.

This prompt took the audit report and executed: updating HelpPanel.tsx content, adding the search state and filtering logic, restructuring the JSX layout, and adjusting styles.

### Prompt 3: Blog Post (about 15 min agent time)

Goal: Document the process for the Technical Blog.

You're reading it.

## Lessons for Solo Devs

#### What Worked

- Batch the boring stuff - Don't try to maintain docs in real-time if you'll skip it. Let them drift, then batch-fix with LLM help

- Sub-agents for large scope - Any task touching 10+ files benefits from parallelized context

- Cost framing - $0.36 to fix months of tech debt? That reframes "should I bother" calculations

- Document the meta - This blog post makes the process repeatable for future audits

The Help panel will drift again. Features will ship without documentation updates. That's fine. Now I have a playbook: every few months, run the audit prompt, let sub-agents parallelize the review, apply fixes. Thirty minutes and pocket change.

## Try the Updated Help Panel

Open EF-Map and click the ? Help button in the top bar. Search for any feature. Check out the Quick Links section at the top. If something's still missing or unclear, give me a shout in Discord or via the EF-Map shoutbox chat.

## Related Posts

- Vibe Coding: Building a 124,000-Line Project Without Writing Code (https://ef-map.com/blog/vibe-coding-large-scale-llm-development) - The development methodology behind EF-Map

- Context7 MCP: Documentation Automation (https://ef-map.com/blog/context7-mcp-documentation-automation) - How we keep LLMs informed about the codebase

- Smart Assembly Size Filtering in 45 Minutes (https://ef-map.com/blog/smart-assembly-size-filtering-45-minutes) - Another example of rapid LLM-assisted development

