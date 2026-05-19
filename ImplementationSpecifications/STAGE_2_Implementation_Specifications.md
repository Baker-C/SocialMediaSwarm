# STAGE 2: Learning & Optimization Specifications

## Overview

**Goal:** Leverage Stage 1 data to discover patterns, optimize posting, and expand with multiple agents per niche using different tones/styles.

**Duration:** ~4 weeks (deploy new accounts, discover patterns, optimize existing ones)

**Scope:** Pattern discovery, multi-agent system, tone tracking, data-driven posting

---

## Part 1: Data Migration from Stage 1

### Retroactive Pattern Tagging

Before new posts are made, run a one-time script:

```
Pattern Discovery & Back-Tagging Script:

1. Analyze all Stage 1 posts:
   ├─ Extract keywords, tone, length, structure
   ├─ Group posts by similarity
   └─ Identify recurring patterns

2. For each discovered pattern:
   ├─ Create Learnings doc
   ├─ Find all Stage 1 posts matching pattern
   ├─ Update Posts docs: add pattern_id
   └─ Create PatternPerformance docs with retroactive data

3. For each Stage 1 account:
   ├─ Analyze all posts
   ├─ Calculate tone scores (which tones appear in high-performing posts)
   ├─ Create AccountTonePreferences doc
   ├─ Populate tone_scores with historical success rates
   └─ Identify top 2-3 tones for account

4. Database cleanup:
   ├─ Remove placeholder Learnings docs
   ├─ Remove empty PatternPerformance docs
   └─ Verify all Stage 1 posts tagged with patterns
```

**Expected Output:**
- 8-15 Learnings docs per niche (patterns discovered)
- All Stage 1 posts tagged with pattern_id
- AccountTonePreferences created for all 5 Stage 1 accounts
- PatternPerformance historical data populated

**Script Execution:** Before deploying Stage 2 accounts

---

## Part 2: New Accounts (Stage 2)

### Multi-Agent Deployment Per Niche

Add 2-3 new accounts per niche with DIFFERENT tones/styles:

```
AI-TRENDS niche (now has 3 accounts):
├─ ai-trends (Stage 1) - Balanced style, inherited tones from Stage 1
├─ ai-research (NEW) - Research-focused, tones: informative, authoritative, educational
└─ ai-critical (NEW) - Critical/skeptical, tones: skeptical, controversial, questioning

CRYPTO-MARKETS niche (now has 3 accounts):
├─ crypto-markets (Stage 1) - Balanced style
├─ defi-bull (NEW) - Bullish/excited, tones: excited, opinionated, humorous
└─ crypto-risk (NEW) - Risk-focused, tones: skeptical, dark, warning

INDIE-HACKER-WINS niche (now has 3 accounts):
├─ indie-hacker-wins (Stage 1) - Balanced
├─ indie-tech (NEW) - Tech-focused, tones: technical, informative, playful
└─ indie-stories (NEW) - Story-focused, tones: opinionated, playful, excited

DESIGN-SYSTEMS niche (now has 3 accounts):
├─ design-systems (Stage 1) - Balanced
├─ design-theory (NEW) - Theory-focused, tones: authoritative, informative, opinionated
└─ design-memes (NEW) - Fun/meme-focused, tones: humorous, playful, sarcastic

CLIMATE-TECH niche (now has 3 accounts):
├─ climate-tech (Stage 1) - Balanced
├─ climate-solutions (NEW) - Solutions-focused, tones: excited, informative, hopeful
└─ climate-urgent (NEW) - Urgent/warning, tones: dark, skeptical, controversial
```

**Total accounts:** 5 (Stage 1) + 10 (Stage 2 new) = 15 accounts

### New Account Configuration

```
Each new account in Accounts collection:
├─ account_id (unique)
├─ niche (same as parent)
├─ status: "active"
├─ followers: 0
├─ system_prompt: (updated for specific tone/style)
├─ tone_preferences_id: (references new AccountTonePreferences doc)
├─ prompt_version: 1
├─ tags: ["stage_2", "{personality_style}"]
└─ notes: "Created in Stage 2, style: {description}"

Example system_prompt for ai-critical:
"You are a critical AI researcher on Twitter.
You focus on limitations, risks, and challenges in AI.
You are skeptical of hype and groundless claims.
Your posts should challenge assumptions and highlight problems.
Tones: skeptical, controversial, questioning.
Length: 150-280 characters.
Include specific examples and citations when possible."
```

---

## Part 3: Collections Changes

### NEW Collections (Now Active)

**1. AccountTonePreferences**
- Create for all 15 accounts (5 Stage 1 + 10 new Stage 2)
- Stage 1 accounts: populated retroactively from their data
- Stage 2 accounts: start with target tones, learn from new posts
- Update: Hourly (after analyzing new posts)

### EXPANDED Collections

**2. Learnings**
- No longer placeholder
- NOW ACTIVE for posting logic
- Use discovered patterns to guide ContentCreator
- Continue updating hourly (discover new patterns)

**3. PatternPerformance**
- NOW ACTIVE, guide posting decisions
- Hourly updates with new data
- Weight: 72-hour data heavily, lifetime data lightly

**4. Posts**
- Now includes: pattern_id (filled), tones (2-3 selected), engagement tracking
- Status: still "posted" (no drafts yet)

### UNCHANGED Collections

**5. EngagementSnapshot** - Continue as is
**6. AccountMetrics** - Continue as is
**7. Accounts** - Updated with new accounts

---

## Part 4: Posting Logic (Stage 2 - Optimized)

### Three-Layer Weighting Strategy

```
For each post, use THREE data sources with DIFFERENT weights:

LAYER 1: Last Hour's Trending Topics
├─ What's trending RIGHT NOW in the niche
├─ Use for: CONTENT DECISION (what to write about)
├─ Weight: 100% (this is what people are talking about)
├─ Source: Twitter trends + Reddit + HackerNews
└─ Decision: "Should I post about scaling laws or safety?"

LAYER 2: Last 72 Hours Historical Performance
├─ What worked in the recent past
├─ Use for: FORMAT/TONE/LENGTH DECISION
├─ Weight: 70% (most important for style)
├─ Source: AccountTonePreferences + Learnings from last 72h
├─ Calculation:
│  ├─ Filter posts from account in last 72h
│  ├─ For each tone: calc success_rate
│  ├─ For each pattern: calc avg_engagement
│  ├─ For each length: calc success_rate
│  └─ Identify best: tone + pattern + length combo
└─ Decision: "Use 'skeptical' tone, research pattern, 200-char length"

LAYER 3: Lifetime Historical Performance
├─ Long-term trends for this account
├─ Use for: BASELINE/GUIDANCE (less important)
├─ Weight: 30% (historical baseline)
├─ Source: Full AccountTonePreferences + Learnings history
└─ Decision: "Overall, this account does well with opinionated tone"

Final Scoring:
├─ For each (tone, pattern, length) combination:
│  ├─ Score = (72h_success * 0.7) + (lifetime_success * 0.3)
│  └─ Pick combination with highest score
└─ ContentCreator uses that combination
```

### ContentCreator Prompt (Stage 2 - Data-Driven)

```
You are creating a post for {account_name} in the {niche} niche.

ACCOUNT PERSONALITY:
- Top tones: {top_3_tones}
- Best performing pattern: {pattern_name}
- Pattern description: {pattern_description}
- Example posts from this pattern: {example_posts}

CURRENT CONTEXT:
- Trending topics RIGHT NOW: {trending_topics}
- Recent performance (72h):
  - Best tone: {best_tone_72h}
  - Best pattern: {best_pattern_72h}
  - Best length: {best_length_72h}

INSTRUCTIONS:
1. Write a post matching:
   - Pattern: {selected_pattern}
   - Tone: {selected_tone} (primary), {selected_tone_2} (secondary)
   - Length: {target_length} characters
   - Content: About the trending topic {main_trending_topic}

2. Follow the pattern template:
   - {pattern.what_makes_similar[0]}
   - {pattern.what_makes_similar[1]}
   - Include a specific example or statistic

3. Use the tone effectively:
   - {tone_guidance}

4. Post should feel authentic for this account while leveraging what works.

Generate ONE post. Output only the post text, nothing else.
```

### Hourly Job (Stage 2 - More Complex)

```
Hourly Schedule (every hour at :00):

├─ 0:00 - Engagement polling (same as Stage 1)
│  ├─ Update EngagementSnapshot for all posts
│  ├─ Create new milestone snapshots (1h, 4h, 12h, 24h, etc.)
│  └─ Recalculate AccountMetrics

├─ 0:05 - Pattern Performance Analysis
│  ├─ For each niche:
│  │  ├─ For each pattern in that niche:
│  │  │  ├─ Find posts from LAST HOUR matching pattern
│  │  │  ├─ Calculate avg_engagement_rate
│  │  │  ├─ Create PatternPerformance hourly snapshot
│  │  │  └─ Score: "Should use this pattern next?"
│  │  └─ Create list of "high engagement patterns" for this hour
│  └─ Store in cache (used in 0:20)

├─ 0:10 - Get trending topics + weighted history
│  ├─ Get trending for each niche
│  ├─ For each account:
│  │  ├─ Query AccountMetrics last 72h
│  │  ├─ Calculate best tones, patterns, lengths (72h)
│  │  ├─ Get lifetime preferences from AccountTonePreferences
│  │  └─ Weight and score: 70% recent, 30% lifetime
│  └─ Create decision package per account

├─ 0:15 - Generate posts (via ContentCreator - NEW LOGIC)
│  ├─ For each account:
│  │  ├─ Get decision package from 0:10
│  │  ├─ Get high-engagement patterns from 0:05
│  │  ├─ Call ContentCreator with:
│  │  │  - Account personality
│  │  │  - Top tones from 72h weighting
│  │  │  - Best pattern from recent performance
│  │  │  - Trending topics from right now
│  │  │  - Suggested length from recent data
│  │  ├─ Get post text back
│  │  ├─ Extract/detect tones from generated text
│  │  └─ Assign pattern_id based on matching template
│  └─ Get 15 candidate posts (one per account)

├─ 0:20 - Safety check (upgraded)
│  ├─ Basic checks (same as Stage 1)
│  ├─ NEW: Pattern-based checks
│  │  ├─ If pattern says "include statistics", verify post has one
│  │  ├─ If pattern says "question format", check for question mark
│  │  └─ Warn if post doesn't match pattern expectations
│  ├─ Approval decision
│  └─ Expected approval rate: ~85-95%

├─ 0:25 - Post to Twitter
│  ├─ For each approved post:
│  │  ├─ Call Twitter API
│  │  ├─ Get twitter_post_id
│  │  ├─ Store in Posts with:
│  │  │  - pattern_id (assigned in 0:15)
│  │  │  - tones (2-3 tones detected/assigned)
│  │  │  - posted_at: now
│  │  └─ Create initial EngagementSnapshot "current"
│  └─ 14-15 posts posted

├─ 0:30 - Hourly Pattern Discovery (continuous learning)
│  ├─ For each account:
│  │  ├─ Analyze posts from LAST 24 HOURS
│  │  ├─ Look for new patterns not yet in Learnings
│  │  ├─ If new pattern detected:
│  │  │  ├─ Create new Learnings doc
│  │  │  ├─ Calculate success_rate on sample
│  │  │  └─ Set status: "validating"
│  │  ├─ For EXISTING patterns:
│  │  │  ├─ Add new posts to sample size
│  │  │  ├─ Recalculate success_rate
│  │  │  ├─ Update PatternPerformance
│  │  │  └─ Check if confidence > 0.7 (validate)
│  │  └─ Update tone scores in AccountTonePreferences
│  │
│  └─ Expected: 1-2 new patterns discovered per week per niche

└─ 0:35 - Done, wait for next hour
```

---

## Part 5: Collections Updates

### AccountTonePreferences (Updated Hourly)

```
For each account, after each hour of posts:

1. Analyze new posts posted this hour
   ├─ Detect tones in post content
   ├─ Check engagement metrics
   └─ If engagement > 5%: mark as "successful"

2. Update tone_scores:
   ├─ For each tone used:
   │  ├─ Increment "uses" count
   │  ├─ If successful: increment "successful_posts"
   │  ├─ Recalculate success_rate
   │  └─ Recalculate avg_engagement_rate
   └─ Updated every hour as posts accumulate

3. Re-rank top_tones:
   ├─ Sort by success_rate
   ├─ Update top 2-3 tones
   ├─ Confidence increases with more data
   └─ Updated hourly

Example progression over Stage 2:
- Week 1: ai-critical account
  - skeptical: 7 uses, 6 successful, 85% success_rate
  - controversial: 7 uses, 5 successful, 71% success_rate
  - informative: 6 uses, 3 successful, 50% success_rate
  
- Week 2:
  - skeptical: 14 uses, 13 successful, 93% success_rate (confidence rising)
  - controversial: 14 uses, 10 successful, 71% success_rate
  - informative: 12 uses, 5 successful, 42% success_rate
  
- Week 4:
  - skeptical: 56 uses, 52 successful, 93% success_rate (high confidence)
  - controversial: 56 uses, 39 successful, 70% success_rate
  - informative: 48 uses, 19 successful, 40% success_rate
```

### Learnings (Updated Hourly)

```
For each niche, for each pattern:

HOURLY UPDATES:
├─ If new posts match pattern:
│  ├─ Increment sample_size
│  ├─ Check if successful (engagement > threshold)
│  ├─ Recalculate success_rate
│  ├─ Update post_frequency (% of posts)
│  ├─ Update evolution tracking
│  └─ Set status: improving/stable/declining
│
├─ If success_rate > 0.8 and sample_size > 20:
│  └─ Status: "active" (validated pattern)
│
└─ If success_rate < 0.6 for 2 weeks:
   └─ Status: "archaic" (failing pattern)
```

---

## Part 6: Dashboard (Stage 2 Additions)

### Keep All Stage 1 Views, Add:

#### 8. Pattern Performance Dashboard
```
For each niche, show:
├─ All patterns discovered
├─ For each pattern:
│  ├─ Success rate (% of posts successful)
│  ├─ Sample size (how many posts)
│  ├─ Avg engagement rate
│  ├─ Post frequency (% of posts in niche)
│  ├─ Status (discovering/validating/active/archaic)
│  ├─ Trend (improving/stable/declining)
│  └─ Top example posts
├─ Filter by: niche, status, success_rate
└─ Graph: success_rate over time per pattern
```

#### 9. Tone Performance Per Account
```
For each account, show:
├─ All 11 tones with their scores
├─ For each tone:
│  ├─ Uses (how many posts used this tone)
│  ├─ Success rate (% successful)
│  ├─ Avg engagement rate
│  ├─ Trend (improving/stable/declining)
│  └─ Bar chart of success rate
├─ Highlight top 2-3 tones
└─ Comparison: how account's tones perform vs niche average
```

#### 10. Niche Cross-Comparison
```
For each niche, compare all accounts in that niche:
├─ Table with columns:
│  ├─ Account name
│  ├─ Top tone
│  ├─ Avg engagement rate
│  ├─ Growth rate
│  ├─ Health score
│  └─ Best performing pattern
├─ Identify overlaps: "All top accounts use informative tone"
├─ Identify differences: "Account A uses long posts, Account B uses short"
└─ Insights: "What do successful accounts in this niche have in common?"
```

#### 11. Pattern Weighting Visualization
```
Show the 3-layer weighting for each account:
├─ Last hour trending: {topics}
├─ Last 72h data (70% weight):
│  ├─ Best tone: {tone} ({success_rate}%)
│  ├─ Best pattern: {pattern} ({success_rate}%)
│  └─ Best length: {length} chars
├─ Lifetime data (30% weight):
│  ├─ Best tone: {tone}
│  └─ Best pattern: {pattern}
└─ Final decision: "Use {tone} tone with {pattern} at {length} chars"
```

---

## Part 7: Implementation Order

```
Phase 1: Back-Tagging (Week 1)
├─ [ ] Run pattern discovery script on Stage 1 data
├─ [ ] Tag all Stage 1 posts with pattern_id
├─ [ ] Create Learnings docs from discovered patterns
├─ [ ] Create AccountTonePreferences for Stage 1 accounts
├─ [ ] Populate PatternPerformance with historical data
└─ [ ] Verify all data properly tagged

Phase 2: Deploy Stage 2 Accounts (Week 1-2)
├─ [ ] Create 10 new account configs (2-3 per niche)
├─ [ ] Create AccountTonePreferences for each new account
├─ [ ] Write system prompts for each personality
├─ [ ] Set up tone target tracking
└─ [ ] Ready for posting

Phase 3: Upgrade Posting Logic (Week 2)
├─ [ ] Update ContentCreator with 3-layer weighting
├─ [ ] Implement 72-hour vs lifetime weighting
├─ [ ] Update SafetyGuardian with pattern checks
├─ [ ] Modify hourly job for new logic
├─ [ ] Test with manual posts before automation
└─ [ ] Verify tone detection and assignment

Phase 4: Launch Stage 2 (Week 2-3)
├─ [ ] Deploy new accounts to Twitter
├─ [ ] Start hourly jobs with new logic
├─ [ ] Monitor for issues
├─ [ ] Verify patterns being discovered
├─ [ ] Verify tone scores updating
└─ [ ] All 15 accounts posting hourly

Phase 5: Dashboard & Analysis (Week 3-4)
├─ [ ] Build views 8-11 (pattern, tone, cross-comparison, weighting)
├─ [ ] Test all dashboard queries
├─ [ ] Manual analysis of Stage 2 patterns emerging
├─ [ ] Identify overlaps between accounts in same niche
├─ [ ] Document what works per niche
└─ [ ] Prepare for Stage 3
```

---

## Part 8: Data Expectations (after Stage 2)

```
By end of Stage 2 (4 weeks later):

Posts: ~9,600 total (15 accounts × 24h × 30 days × ~1 post/h)
Stage 1 posts: ~3,000 (original)
Stage 2 posts: ~6,600 (new)

Learnings: 30-50 patterns discovered per niche × 5 niches = 150-250 total
- Stage 1 patterns: ~40-60 patterns
- Stage 2 new patterns: ~100-200 patterns

AccountTonePreferences: 15 docs
- Stage 1 (5 accounts): Populated retroactively
- Stage 2 (10 accounts): Growing over 4 weeks

PatternPerformance: ~3,600 hourly snapshots (continuing from Stage 1)

AccountMetrics: ~7,200 hourly snapshots (15 accounts × 24h × 30 days)

EngagementSnapshot: ~105,600 total (~9,600 posts × 11 snapshots)

Niche-Level Data:
- Patterns per niche: 30-50 (ranked by success rate)
- Tones per niche: Top performers identified
- Account overlaps: Clear picture of what works in each niche
```

---

## Part 9: Success Criteria for Stage 2

✅ All 15 accounts posting reliably every hour
✅ Patterns discovered (30-50 per niche)
✅ AccountTonePreferences showing clear tone preferences per account
✅ 3-layer weighting logic working (72h > lifetime weighting)
✅ Engagement improving compared to Stage 1 (higher avg engagement rates)
✅ Tone optimization showing measurable impact (+5-10% engagement improvement)
✅ Cross-account patterns identified within niches
✅ Dashboard showing clear insights about what works per niche
✅ New Stage 2 accounts performing comparably to optimized Stage 1 accounts
✅ Pattern discovery continuous (1-2 new patterns per week per niche)

---

## Part 10: Stage 2 -> Stage 3 Transition

**Do NOT do:**
- Delete any accounts or data
- Stop hourly jobs
- Reset metrics

**Do:**
- Deploy NicheAnalysis collection
- Deploy NicheEvolution collection
- Expand ContentCreator to consider global patterns
- Enable auto-niche creation from trending topics
- Set up account creation/deletion based on engagement threshold
- Build Stage 3 dashboard views

**Carry Forward:**
- All 15 accounts (keep running)
- All Stage 1 + Stage 2 posts and engagement data
- All Learnings (now complete patterns)
- All AccountTonePreferences (continue learning)
- All hourly jobs (enhanced in Stage 3)
- Dashboard (update with Stage 3 views)

---

## Key Changes from Stage 1

| Aspect | Stage 1 | Stage 2 |
|--------|---------|---------|
| Accounts | 5 | 15 |
| Posting logic | Random trending | Weighted 3-layer |
| Patterns | Stored, not used | Actively used |
| Tones | Stored, not used | Actively tracked & used |
| Niche analysis | Basic | Per-niche patterns identified |
| Account optimization | None | Per-tone optimization |
| Discovery | Hourly (new) | Hourly (update existing) |
| Dashboard | 7 views | 11 views |
| Cross-account learning | No | Yes (within niche) |

---

## Storage & Cost Estimates

**Storage (end of Stage 2):**
- Posts: ~100MB (9,600 posts × 10KB)
- EngagementSnapshots: ~300MB (105,600 docs × 3KB)
- AccountMetrics: ~72MB (7,200 docs × 10KB)
- Learnings: ~10MB (200 patterns × 50KB)
- AccountTonePreferences: ~1MB (15 docs × 60KB)
- PatternPerformance: ~36MB (3,600 docs × 10KB)
- Total: ~520MB (still very manageable)

**Compute:**
- Hourly job: ~90 seconds per run (15 accounts instead of 5)
- Pattern discovery: ~30 seconds per hour
- Dashboard queries: <500ms each
- Total: ~2 minutes per hour

**Cost (estimate):**
- Twitter API: $0 (free tier)
- Claude API: ~$20-30 (25,000 API calls × 1000 tokens)
- RavenDB: Free (local instance)
- Total: ~$30/month
