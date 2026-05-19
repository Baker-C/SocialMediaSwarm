# STAGE 3: Expansion & Global Optimization Specifications

## Overview

**Goal:** Scale to infinite niches, discover new opportunities, create new accounts intelligently, and optimize globally based on Stage 1-2 learnings.

**Duration:** Ongoing (continuous expansion and optimization)

**Scope:** Auto-niche discovery, cross-niche pattern sharing, global analysis, smart account creation/deletion, profitability analysis

---

## Part 1: Niche Management

### Dynamic Niche Creation

#### Auto-Niche Discovery Process

```
Continuous Job (every 6 hours):

├─ 1. Identify Trending Topics
│  ├─ Query Twitter trending globally + by region
│  ├─ Query Reddit trending subreddits
│  ├─ Query HackerNews
│  ├─ Query Product Hunt
│  ├─ Filter: Keep topics with:
│  │  ├─ >10K mentions in last 24h
│  │  ├─ Growth rate >20% (trending up)
│  │  └─ NOT already covered by existing niche
│  └─ Create candidate list

├─ 2. Evaluate Niche Potential
│  ├─ For each candidate topic:
│  │  ├─ Estimate audience size (Twitter followers in topic)
│  │  ├─ Estimate growth rate (speed of trend)
│  │  ├─ Estimate engagement (average engagement in topic)
│  │  ├─ Estimate competition (how many accounts already cover it)
│  │  ├─ Calculate opportunity_score:
│  │  │  opportunity_score = (audience × growth × engagement) / (competition + 1)
│  │  └─ Keep if opportunity_score > threshold
│  └─ Rank by opportunity_score

├─ 3. Check Against Existing Niches
│  ├─ For each candidate:
│  │  ├─ Check if topic overlaps with existing niche
│  │  ├─ If overlap >70%: merge into existing niche (don't create new)
│  │  └─ If overlap <30%: create new niche
│  └─ Final list: true new niches

├─ 4. Create New Niche
│  ├─ For each approved new niche:
│  │  ├─ Create niche record in database
│  │  ├─ Create NicheAnalysis placeholder doc
│  │  ├─ Kick off initial pattern discovery
│  │  ├─ Schedule first account creation
│  │  └─ Mark as "exploring" (not "stable" yet)
│  └─ Ready for account creation

└─ 5. Monitor Trending Status
   ├─ For each "exploring" niche:
   │  ├─ If engagement_rate > threshold for 7 days straight:
   │  │  └─ Status: "stable" (keep it)
   │  ├─ If engagement_rate < threshold for 7 days:
   │  │  └─ Status: "paused" (stop creating accounts, watch)
   │  └─ If engagement_rate stays low for 30 days:
   │     └─ Status: "failed" (archive niche)
   └─ Continuous monitoring
```

#### Niche Stability States

```
"exploring"
  ├─ New niche, <7 days old
  ├─ Creating initial accounts
  ├─ Gathering data
  └─ Will move to "stable" or "paused"

"stable"
  ├─ Niche proven (engagement > threshold for 7+ days)
  ├─ Can create more accounts (up to cap)
  ├─ Continuing optimization
  └─ Status until engagement fails

"paused"
  ├─ Engagement dropped below threshold
  ├─ Stop creating new accounts
  ├─ Keep existing accounts running
  ├─ Monitor for recovery
  └─ If recovers: back to "stable"

"failed"
  ├─ Low engagement for 30+ days
  ├─ Archive niche
  ├─ Mark accounts as inactive
  ├─ Keep historical data
  └─ May resurrect if topic trends again
```

---

## Part 2: Intelligent Account Creation

### Account Creation Trigger

```
When to create new accounts:

1. New niche created (from niche discovery):
   ├─ Create initial account (personality TBD)
   ├─ Wait 7 days to collect data
   └─ If engagement good, create more

2. Existing niche with high opportunity:
   ├─ If niche has 1-2 accounts and high engagement:
   │  ├─ Create new account with different tone/style
   │  ├─ Test new personality mix
   │  └─ See if it outperforms existing
   └─ Cap: 3-5 accounts per "stable" niche (configurable)

3. Cross-niche pattern opportunity:
   ├─ If pattern X works great in ai-trends:
   │  ├─ Create account in crypto-markets using same pattern
   │  ├─ Adapt personality to match crypto audience
   │  └─ Test if pattern transfers
   └─ Only for highest-confidence patterns (>0.85 success_rate)

4. Global optimization:
   ├─ If system health score low:
   │  ├─ Don't create new accounts
   │  └─ Focus on improving existing
   └─ If system health score high:
      └─ Can take more risks on new accounts
```

### Account Creation Decision Logic

```
CREATE NEW ACCOUNT IF:
├─ niche.status == "stable" AND
├─ niche.accounts_count < max_per_niche AND
├─ niche.avg_engagement > threshold AND
├─ (
│  ├─ niche.age > 7 days OR
│  ├─ pattern_opportunity_detected OR
│  └─ new_niche_created
│ ) AND
├─ system_health_score > min_threshold AND
├─ global_account_count < hard_cap

THEN:
├─ Select personality (tone combination):
│  ├─ From patterns that work in niche
│  ├─ Different from existing accounts
│  └─ Consider cross-niche patterns
├─ Create account
├─ Deploy to Twitter
├─ Start hourly posting
└─ Mark as "stage_3_new"

ELSE:
└─ Don't create, wait for better conditions
```

---

## Part 3: Intelligent Account Deletion/Archival

### Account Deletion Trigger

```
DELETE/ARCHIVE ACCOUNT IF:
├─ health_score < 40 AND
├─ health_score declining for 14+ days AND
├─ (
│  ├─ niche is "failed" OR
│  ├─ account.status == "stagnant"
│ ) AND
├─ account.age > 30 days

THEN:
├─ Set status: "archived"
├─ Stop posting
├─ Keep all historical data
├─ Track why it failed
└─ Release account slot for new account

ELSE IF:
├─ niche.status == "paused" AND
├─ account.age < 7 days

THEN:
├─ Keep running (less than 7 days, needs more data)
├─ Monitor closely
└─ Delete only if niche still low after 30 days total
```

---

## Part 4: Collections (Stage 3 Activation)

### NEW Collections (Now Active)

**1. NicheAnalysis**
- Compute: Every 12 hours
- Store: Current niche snapshot
- Use for: Niche rankings, opportunity scoring, comparison
- Fields:
  ```
  {
    "niche": "string",
    "timestamp": "timestamp",
    "ecosystem": {
      "accounts_active": number,
      "accounts_failed": number,
      "total_followers": number
    },
    "performance": {
      "avg_engagement_rate": number,
      "avg_growth_rate": number,
      "engagement_trend": "improving | stable | declining"
    },
    "opportunity": {
      "saturation_score": 0.0-1.0,
      "opportunity_score": 0.0-1.0,
      "recommendation": "expand | maintain | pause | kill"
    }
  }
  ```

**2. NicheEvolution**
- Store: Every 12-hourly NicheAnalysis snapshot
- Retention: Forever
- Use for: Trend analysis, "when did this niche peak?", historical comparison

**3. GlobalAnalysis** (new, computed regularly)
- Compute: Every 24 hours
- Store: Global snapshot across all niches
- Fields:
  ```
  {
    "timestamp": "timestamp",
    "system_stats": {
      "total_accounts": number,
      "total_niches": number,
      "total_followers": number,
      "total_posts": number
    },
    "global_performance": {
      "avg_engagement_rate": number,
      "healthy_accounts_percent": number,
      "struggling_accounts_percent": number
    },
    "niche_rankings": [
      { "niche": string, "engagement_rate": number, "growth_rate": number }
    ],
    "opportunity_ranking": [
      { "niche": string, "opportunity_score": number }
    ],
    "universal_patterns": [
      { "pattern_id": string, "works_in_niches": [niche, niche], "success_rate": number }
    ],
    "recommendations": {
      "expand_into": ["niche1", "niche2"],
      "pause": ["niche3"],
      "kill": ["niche4"],
      "priority_patterns": ["pattern1", "pattern2"]
    }
  }
  ```

**4. GlobalEvolution**
- Store: Daily GlobalAnalysis snapshots
- Retention: Forever
- Use for: Month-over-month analysis, "is system growing?"

### Cross-Niche Pattern Analysis

```
NEW Learnings field: works_across_niches
├─ Pattern discovered in ai-trends
├─ We test it in crypto-markets (different account)
├─ If successful there too:
│  ├─ Add to pattern.works_across_niches: ["ai-trends", "crypto-markets"]
│  ├─ Calculate global_success_rate (across all niches)
│  └─ Mark as "universal_pattern"
└─ Use for smart account creation

Example:
Pattern: "research-announcements"
├─ Works in: ai-trends (92% success)
├─ Works in: climate-tech (89% success)
├─ Works in: crypto-markets (78% success)
├─ Global success rate: 86%
├─ Recommendation: Try in remaining niches
└─ Status: "universal_pattern"
```

---

## Part 5: Updated Posting Logic (Stage 3)

### Four-Layer Weighting (instead of three)

```
LAYER 1: Last Hour Trending (30%)
├─ GLOBAL trending topics (all platforms)
├─ Use for: General content direction
├─ Weight: 30%
└─ Decision: "What are people talking about right now?"

LAYER 2: Last Hour Niche Trending (30%)
├─ Trending WITHIN this niche specifically
├─ Use for: Niche-specific angle
├─ Weight: 30%
└─ Decision: "What's trending in THIS niche right now?"

LAYER 3: Last 72 Hours Niche Patterns (25%)
├─ Best patterns in THIS niche (recent)
├─ Use for: Format/tone/length
├─ Weight: 25%
└─ Decision: "What format works in this niche recently?"

LAYER 4: Universal Patterns (15%)
├─ Patterns that work across ALL niches
├─ Use for: Baseline guarantee
├─ Weight: 15%
└─ Decision: "What's proven to work globally?"

Final Scoring:
├─ For each (pattern, tone, length) combo:
│  ├─ Score = (global_trend * 0.3) +
│  │           (niche_trend * 0.3) +
│  │           (niche_patterns_72h * 0.25) +
│  │           (universal_patterns * 0.15)
│  └─ Pick highest scoring combo
└─ ContentCreator uses that
```

### ContentCreator Prompt (Stage 3)

```
You are creating a post for {account_name} in {niche} niche.

ACCOUNT PROFILE:
- Top tones: {tone1}, {tone2}, {tone3}
- Best patterns: {patterns}

NICHE CONTEXT:
- Trending in this niche: {niche_trends}
- Best format (72h): {pattern_from_niche}
- Pattern performance: {success_rate}

GLOBAL CONTEXT:
- Trending globally: {global_trends}
- Universal patterns working everywhere: {universal_patterns}
- This niche performance vs global: {comparison}

WEIGHTING:
- Use 30% global trends, 30% niche trends
- Use 25% niche patterns, 15% universal patterns
- Balance breadth (global relevance) with depth (niche expertise)

INSTRUCTIONS:
1. Write post about intersection of:
   - Global trending topic {global_topic}
   - Niche trending topic {niche_topic}
   - Using pattern: {selected_pattern}

2. Format:
   - Pattern style: {pattern_requirements}
   - Tone: {tone1} + {tone2}
   - Length: {target_length}

3. Make it specific to {niche} while appealing to global audience

Generate ONE post. Output only post text.
```

---

## Part 6: Dashboard (Stage 3 Additions)

### Keep All Previous Views, Add:

#### 12. Global Dashboard
```
Show system-wide metrics:
├─ Total accounts: {count}
├─ Total niches: {count}
├─ Total followers: {count}
├─ Average engagement rate: {%}
├─ System health score: {0-100}
├─ Accounts by status: active/paused/archived pie chart
├─ Growth trend: graph over time
└─ Alerts: any critical issues
```

#### 13. Niche Opportunity Scoreboard
```
For each niche, show:
├─ Niche name
├─ Status: exploring | stable | paused | failed
├─ Opportunity score: 0.0-1.0
├─ Recommendation: expand | maintain | pause | kill
├─ Accounts in niche: count
├─ Avg engagement: {%}
├─ Growth rate: {%}
├─ Saturation: low | medium | high
├─ Days until review: count
└─ Sort by: opportunity_score (highest first)
```

#### 14. Cross-Niche Pattern Analysis
```
Show which patterns work across niches:
├─ Pattern name
├─ Niches where it works: [niche1, niche2, niche3]
├─ Success rate per niche: table
├─ Global success rate: {%}
├─ Recommendation: "Try in {niche}"
├─ Filter by: universal | niche_specific
└─ Graph: success rate per niche for selected pattern
```

#### 15. Account Creation/Deletion Log
```
Show history of account decisions:
├─ Account name
├─ Action: created | archived | paused
├─ Reason: niche_created | high_opportunity | stagnation | niche_failed
├─ Date
├─ Final engagement rate
├─ Final follower count
├─ Days active
└─ Filter by: action, reason, date range
```

#### 16. Profitability Analysis (if monetized)
```
For each niche/account, show:
├─ Follower count
├─ Engagement rate
├─ Revenue (if applicable): sponsorships, affiliate, ads
├─ Cost: API, compute, etc.
├─ Net profit
├─ ROI: %
├─ Profit per follower gained
├─ Rank by: profitability, ROI, profit_per_follower
└─ Chart: profitability trend per niche
```

#### 17. Niche Age & Performance
```
Track how niches perform as they age:
├─ X-axis: Days since niche creation
├─ Y-axis: Engagement rate
├─ Each line: different niche
├─ Show: which age has highest engagement?
├─ Insight: "New niches perform well for first 14 days, then stabilize"
└─ Use for: predicting when niche will stabilize
```

#### 18. Account Maturity Curve
```
Track how accounts improve as they age:
├─ X-axis: Days since account creation
├─ Y-axis: Engagement rate
├─ Lines grouped by: tone combination, pattern focus
├─ Show: learning curve for different account types
├─ Insight: "Skeptical accounts take longer to find audience"
└─ Use for: predicting when to judge if account works
```

---

## Part 7: Implementation Order

```
Phase 1: Auto-Niche Discovery (Weeks 1-2)
├─ [ ] Build trending topic identification system
├─ [ ] Build opportunity scoring algorithm
├─ [ ] Deploy NicheAnalysis collection
├─ [ ] Create initial niche discovery job (6-hourly)
├─ [ ] Test on Stage 2 niches (should find new adjacent topics)
├─ [ ] Deploy NicheEvolution collection
└─ [ ] Verify niche monitoring working

Phase 2: Smart Account Management (Weeks 2-3)
├─ [ ] Build account creation decision logic
├─ [ ] Build account deletion/archival logic
├─ [ ] Build engagement threshold system (configurable from dashboard)
├─ [ ] Implement account creation trigger
├─ [ ] Deploy to test (create 1 test account in new niche)
├─ [ ] Monitor for 7 days
└─ [ ] If successful, deploy to production

Phase 3: Cross-Niche Pattern Sharing (Week 3)
├─ [ ] Build pattern testing framework
├─ [ ] Select 1 high-confidence pattern from Stage 2
├─ [ ] Create test account in different niche using that pattern
├─ [ ] Monitor for 14 days
├─ [ ] If successful: add to universal_patterns
├─ [ ] Automate pattern recommendation system
└─ [ ] Deploy cross-niche account creation

Phase 4: Global Analysis (Week 4)
├─ [ ] Build GlobalAnalysis computation
├─ [ ] Build GlobalAnalysis storage
├─ [ ] Deploy GlobalEvolution for history
├─ [ ] Compute daily global snapshots
├─ [ ] Generate niche recommendations
├─ [ ] Build ranking system (best niches, best patterns, etc.)
└─ [ ] Ready for Stage 3 dashboard views

Phase 5: Dashboard & Monitoring (Week 4-5)
├─ [ ] Build views 12-18 (global, niche opportunity, cross-pattern, etc.)
├─ [ ] Test all dashboard queries
├─ [ ] Set up alerts (health score drops, niche fails, etc.)
├─ [ ] Manual analysis of emerging patterns
├─ [ ] Document system behavior at scale
└─ [ ] Prepare for continuous optimization

Phase 6: Continuous Optimization (Ongoing)
├─ [ ] Monitor niche discovery (create new niches as opportunities appear)
├─ [ ] Monitor account performance (create/delete as needed)
├─ [ ] Monitor pattern effectiveness (identify universal patterns)
├─ [ ] Monitor system health (adjust thresholds as needed)
├─ [ ] Weekly reporting on system state
└─ [ ] Quarterly strategy review (scale direction)
```

---

## Part 8: Configuration (Adjustable from Dashboard)

```
Niche Management:
├─ min_opportunity_score: 0.5 (create niche if > this)
├─ stability_threshold: 0.05 (engagement rate minimum)
├─ stability_window: 7 days (must maintain X rate for Y days)
├─ max_accounts_per_niche: 5 (hard cap per niche)
├─ max_total_accounts: 100 (global hard cap)
├─ niche_review_interval: 24 hours (how often check niche status)
└─ niche_failure_window: 30 days (archive if low for 30 days)

Account Management:
├─ health_score_delete_threshold: 40 (archive if < this)
├─ health_score_decline_window: 14 days (archive if declining 14 days)
├─ new_account_observation_period: 7 days (wait before deciding)
├─ min_data_for_evaluation: 50 posts (before judging account)
└─ stagnation_threshold: 2 weeks no growth

System Health:
├─ min_health_for_new_accounts: 50 (out of 100)
├─ health_score_alert_threshold: 40 (alert if below this)
├─ engagement_alert_threshold: 0.03 (alert if below 3%)
└─ growth_alert_threshold: 0.05 (alert if <5% per week)

Pattern Sharing:
├─ min_pattern_confidence_for_sharing: 0.85
├─ cross_niche_test_window: 14 days
├─ cross_niche_success_threshold: 0.70
└─ universal_pattern_min_niches: 3 (works in 3+ niches)

Global:
├─ computation_frequency: 24 hours (how often refresh global analysis)
├─ discovery_frequency: 6 hours (how often check for new niches)
├─ hourly_job_timeout: 300 seconds (timeout if exceeds)
└─ data_retention: forever (keep all historical data)
```

---

## Part 9: Data Expectations (Ongoing)

```
After 12 weeks (Stage 1 + 2 + 3):

Accounts: 15-100 (depending on niche discovery success)
├─ Stage 1: 5 accounts
├─ Stage 2: 10 accounts
├─ Stage 3: 0-85 accounts (depends on opportunities)
└─ Active ratio: ~80% (some archived)

Niches: 5-20+
├─ Stage 1-2: 5 stable niches
├─ Stage 3: 0-15+ new niches
├─ Status breakdown: 80% stable, 15% exploring, 5% paused/failed

Posts: 50,000-100,000+
├─ Hourly posting × accounts × hours
├─ At 50 accounts × 24h × 90 days = 108,000 posts
└─ Engagement data: ~1.2M EngagementSnapshot docs

Learnings: 200-500+ patterns
├─ 30-50 per stable niche × 5 = 150-250
├─ 30-50 per new niche × 10 = 300-500
├─ Many overlapping/redundant (consolidated to unique patterns)
└─ 50+ universal patterns (work across niches)

AccountTonePreferences: 50-100+
├─ Clear tone preferences per account
├─ Tone success rates high confidence
└─ Emerging patterns: "skeptical tones underperform in certain niches"

NicheAnalysis: 1 per niche (current snapshots)
NicheEvolution: 1440+ docs (12h × 60 days × 2 niches, by end)
GlobalAnalysis: 1 (current)
GlobalEvolution: 60+ docs (daily × 60 days)
```

---

## Part 10: Success Criteria for Stage 3

✅ Auto-niche discovery working (discovering 1+ new niche per week)
✅ Account creation/deletion logic working (accounts added/removed as needed)
✅ 50-100 accounts active (stable state)
✅ 15-20+ niches (mix of Stage 2 originals + new discoveries)
✅ Universal patterns identified (15-20 patterns work across niches)
✅ Cross-niche pattern sharing working (patterns transferred between niches)
✅ Global dashboard showing clear system health
✅ Profitability analysis available (if monetized)
✅ System self-sustaining (minimal manual intervention needed)
✅ Continuous optimization working (system improving automatically)

---

## Part 11: Long-Term Vision (Post-Stage 3)

```
After Stage 3 Stabilizes (3+ months):

Possible Expansions:
├─ Multi-platform (Twitter → TikTok, LinkedIn, Instagram)
├─ Multi-language (expand beyond English)
├─ Monetization integration (affiliate links, sponsorships, ads)
├─ Agent specialization (recruiting agents instead of generation)
├─ Community building (replies, engagement, community management)
├─ Content curation (retweet best content in niche)
├─ Hashtag optimization
└─ Trend prediction (predict trends before they happen)

Optimization Areas:
├─ Better tone detection (more granular than 11 tones)
├─ Better pattern definition (more specific templates)
├─ Better niche definition (overlap detection, merger logic)
├─ Better account matching (optimal personality for niche)
├─ Better timing (post at optimal times per account per day)
├─ Better cross-platform strategy (what works on Twitter vs TikTok?)
└─ Better monetization (which niches are most profitable?)

Advanced Features:
├─ Predictive account health (know if account will fail before it does)
├─ Trend prediction (identify trends 1-2 weeks early)
├─ Sentiment analysis of replies (understand audience perception)
├─ Competitor analysis (track what competitors doing in niche)
├─ Audience growth prediction (estimate max followers per niche)
└─ Revenue optimization (maximize $ per post)
```

---

## Key Architecture Decisions

| Decision | Stage 1 | Stage 2 | Stage 3 |
|----------|---------|---------|---------|
| Niches | 5 fixed | 5 fixed | Dynamic (5+) |
| Accounts | 5 | 15 | 15-100+ |
| Posting logic | Random trending | 3-layer weighted | 4-layer weighted |
| Pattern use | Stored only | Active optimization | Cross-niche sharing |
| Niche analysis | Basic | Per-niche detailed | Global + per-niche |
| Account creation | Manual | Strategic | Automatic (thresholds) |
| Account deletion | Manual | Decision logic | Automatic (thresholds) |
| Dashboard | 7 views | 11 views | 18 views |
| System health | Manual | Measured | Auto-optimized |

---

## Storage & Cost Estimates (Ongoing)

**Storage (end of Stage 3):**
- Posts: ~1-2GB (100K+ posts)
- EngagementSnapshots: ~3-4GB (1M+ snapshots)
- AccountMetrics: ~300MB
- Learnings: ~50MB (500+ patterns)
- NicheAnalysis/Evolution: ~100MB
- GlobalAnalysis/Evolution: ~10MB
- AccountTonePreferences: ~5MB
- **Total: ~5-7GB** (manageable, but start considering archival)

**Compute:**
- Hourly job: ~2-5 minutes (50-100 accounts)
- Pattern discovery: ~1 minute per hour
- Niche discovery: ~2 minutes (6-hourly)
- Global analysis: ~5 minutes (daily)
- Dashboard queries: <500ms each
- **Total: ~8-12 minutes per hour**

**Cost (estimate):**
- Twitter API: $0 (free tier) or $100-300/month (if paid tier needed at scale)
- Claude API: ~$100-200/month (100K posts × 1000 tokens)
- RavenDB: Free (local) or $50-200/month (if cloud)
- Compute: $20-50/month (if cloud)
- **Total: $170-550/month**

---

## Scaling Beyond Stage 3

If system grows beyond 100 accounts / 20+ niches:

```
Next Considerations:
├─ Database sharding (by niche, by account type)
├─ Compute distribution (worker nodes for hourly jobs)
├─ Multi-region deployment (reduce latency)
├─ Advanced caching (Redis for hot data)
├─ Batch processing (daily vs hourly updates)
├─ Alert system (proactive monitoring)
└─ A/B testing framework (test new features safely)

At 500+ accounts:
├─ Move to cloud database (RavenDB Cloud)
├─ Deploy worker nodes
├─ Implement caching layer
├─ Add data warehouse (historical analytics)
└─ Hire ops team to manage

At 1000+ accounts:
├─ Full distributed system
├─ Dedicated infrastructure
├─ Advanced ML for predictions
├─ Dedicated data team
└─ Consider pivot to platform
```
