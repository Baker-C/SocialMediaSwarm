# STAGE 1: Foundation & Data Collection Specifications

## Overview

**Goal:** Build a stable foundation with 5 accounts posting hourly, gathering comprehensive data without using it for optimization yet.

**Duration:** ~4 weeks (accumulate ~3600 posts + engagement data)

**Scope:** Simple, reliable, data-focused

---

## Part 1: Accounts Setup

### Accounts to Deploy

```
5 accounts, different niches, no personality optimization:

1. Account ID: ai-trends
   Niche: AI/ML Research & Trends
   Initial posting strategy: Random high-quality posts about AI
   
2. Account ID: crypto-markets
   Niche: Cryptocurrency & Blockchain
   Initial posting strategy: Random posts about crypto news/prices
   
3. Account ID: indie-hacker-wins
   Niche: Indie Hacking & Startups
   Initial posting strategy: Random posts about indie dev wins
   
4. Account ID: design-systems
   Niche: Design Systems & UI/UX
   Initial posting strategy: Random posts about design
   
5. Account ID: climate-tech
   Niche: Climate Technology & Sustainability
   Initial posting strategy: Random posts about climate tech
```

### Account Configuration (Minimal)

Each account in Accounts collection:
- account_id
- niche
- twitter_handle
- status: "active"
- followers: 0
- system_prompt: "Generate a post about {niche}. Focus on accuracy and interesting insights. Post length: 150-280 characters."
- NO tone_preferences_id (we're not using tones yet)
- NO special personality

---

## Part 2: Collections to Deploy

### ACTIVE Collections (Use fully)

**1. Posts**
- Store every post generated
- Fields: post_id, account_id, niche, content, status, posted_at, created_at, tones (empty array for now), pattern_id (null)
- Status: "posted" (no draft/rejection logic yet)
- Purpose: Complete record of all content

**2. Accounts**
- One doc per account
- Update: followers (hourly from Twitter API), posts_total (running count)
- Purpose: Account registry and status

**3. EngagementSnapshot**
- Store snapshots at: 1h, 4h, 12h, 24h, 48h, 72h, 96h, 120h, 148h, 172h, current
- Update engagement every hour
- Purpose: Track how posts grow over time

**4. AccountMetrics**
- Hourly cache (14-day rolling window)
- Calculate: avg_engagement_rate, health_score, follower_growth_rate, etc.
- Update: Every hour after posts are analyzed
- Purpose: Account performance snapshots

### STORED Collections (Store data, don't use for posting)

**5. Learnings**
- Create empty doc per collection as placeholder
- Will be populated during pattern discovery (Stage 2)
- DO NOT use for posting in Stage 1
- Fields stored: pattern_name, pattern_id, niche, template (empty), status: "discovering"
- Purpose: Ready for Stage 2

**6. PatternPerformance**
- Hourly snapshots stored
- Will track which patterns work (once patterns discovered in Stage 2)
- For now: empty or placeholder docs
- Purpose: Historical tracking starting now

### SKIP Collections (Not deployed yet)

**7. AccountTonePreferences** ← Deploy in Stage 2
**8. NicheAnalysis** ← Deploy in Stage 3
**9. NicheEvolution** ← Deploy in Stage 3

---

## Part 3: Data Collection Strategy

### Per Post - Collect:

```
Posts Collection Stores:
├─ Content + metadata
├─ Engagement over time (via EngagementSnapshot)
├─ Posted timestamp
└─ Niche + account_id

Post Analysis (compute hourly, store in separate analysis cache):
├─ Keywords extracted (NLP)
├─ Tone detected (via Claude) [stored as array, currently unused]
├─ Length (character count)
├─ Structure (has CTA, has question, has numbers)
├─ Sentiment (positive/negative/neutral)
└─ (Do NOT store tones in Posts yet - just compute)
```

### Per Account - Collect:

```
AccountMetrics Stores Hourly:
├─ avg_engagement_rate (% of posts with engagement > 0)
├─ avg_likes, avg_replies, avg_retweets
├─ engagement_variance (consistency)
├─ follower_growth_rate
├─ followers_gained_this_hour
├─ posts_this_hour, posts_this_day, posts_total
├─ health_score (composite)
└─ last_updated timestamp
```

### Global Analysis (compute but store separately):

```
Per Post:
├─ Best posts (top 5 by engagement rate)
├─ Worst posts (bottom 5)
├─ Average engagement by time of day
└─ Average engagement by niche

Per Account:
├─ Total followers gained
├─ Avg engagement rate
├─ Posts generated
├─ Growth rate
└─ Health score

Per Niche:
├─ Which niche has highest engagement
├─ Which niche has fastest growth
├─ Which niche has most posts
└─ Total reach per niche
```

---

## Part 4: Posting Logic (Stage 1 - Simple)

### Hourly Posting Job (runs :00 of every hour)

```
For each account:
  1. Get trending topics for that niche (via Twitter/Reddit/HN API)
  2. ContentCreator agent:
     - Input: niche, trending topics from last hour
     - No pattern logic
     - No tone optimization
     - No historical data weighting
     - Just: "Generate an interesting, accurate post about {niche} and these trending topics"
     - Output: post content (150-280 chars)
  
  3. SafetyGuardian:
     - Basic checks: misinformation, harassment, spam, length
     - Approval probability: ~80-90% (simple checks)
  
  4. Post to Twitter if approved
  
  5. Create EngagementSnapshot for "current" (first check)
  
  6. Store in Posts collection
     - status: "posted"
     - posted_at: now
     - twitter_post_id: from Twitter response
     - tones: [] (empty array, not used)
     - pattern_id: null
     - engagement_snapshots: { "current": snapshot_id }
```

### ContentCreator Prompt (Stage 1)

```
You are a social media expert creating posts for {niche}.

Your goal: Generate an engaging, accurate, interesting post about {niche}.

Trending topics right now:
{trending_topics_list}

Requirements:
- Length: 150-280 characters
- Be specific (include numbers, names, dates when relevant)
- Be interesting (ask questions, make observations, take mild positions)
- Accurate (don't make up facts)
- Tone: varies naturally with topic (no forced personality)

Generate ONE post. Output only the post text, nothing else.
```

---

## Part 5: Hourly Job Flow

```
Hourly Schedule (every hour at :00):
├─ 0:00 - Check Twitter engagement on previous posts
│  ├─ For each post posted in last hour:
│  │  ├─ Query Twitter API for likes, replies, retweets
│  │  ├─ Create/update "current" EngagementSnapshot
│  │  └─ If post is 1h old, also create "1h" EngagementSnapshot
│  │     (similarly for 4h, 12h, 24h, etc.)
│  └─ Recalculate AccountMetrics for all accounts
│
├─ 0:05 - Get trending topics per niche
│  ├─ ai-trends: Query Twitter trends + Reddit r/MachineLearning
│  ├─ crypto-markets: Query Twitter trends + Reddit r/cryptocurrency
│  ├─ indie-hacker-wins: Query Twitter trends + HackerNews
│  ├─ design-systems: Query Twitter trends + Designer blogs
│  └─ climate-tech: Query Twitter trends + Climate subreddits
│
├─ 0:10 - Generate posts (via ContentCreator)
│  ├─ For each account:
│  │  ├─ Call ContentCreator with trending topics
│  │  ├─ Get post text back
│  │  └─ Pass to SafetyGuardian
│  └─ Get 5 candidate posts (one per account)
│
├─ 0:15 - Safety check (via SafetyGuardian)
│  ├─ For each post:
│  │  ├─ Check: misinformation, harassment, spam, length
│  │  ├─ Approval decision
│  │  └─ If rejected: log reason, discard post
│  └─ Expected approval rate: ~80-90%
│
├─ 0:20 - Post to Twitter
│  ├─ For each approved post:
│  │  ├─ Call Twitter API POST /tweets
│  │  ├─ Get twitter_post_id
│  │  └─ Store in Posts collection
│  └─ 4-5 posts posted
│
└─ 0:25 - Done, wait for next hour
```

---

## Part 6: Dashboard (Stage 1)

### Views to Build

#### 1. Post Browser
```
Show:
├─ All posts (reverse chronological)
├─ Per post:
│  ├─ Content
│  ├─ Posted time
│  ├─ Account
│  ├─ Niche
│  ├─ Current engagement (likes, replies, retweets)
│  └─ Engagement rate
├─ Filter: by account, by niche, by date range
└─ Sort: by date, by engagement, by account
```

#### 2. Account Dashboard
```
For each account, show:
├─ Current follower count
├─ Follower growth (this hour, today, lifetime)
├─ Posts posted today
├─ Avg engagement rate (today, 7 days, lifetime)
├─ Health score
├─ Growth trend (improving/stable/declining)
└─ Button to view all posts from this account
```

#### 3. Engagement Timeline (per account)
```
Show:
├─ All posts from account X (reverse chronological)
├─ Each post with:
│  ├─ Content snippet
│  ├─ Posted time
│  ├─ Current engagement
│  └─ Engagement rate
├─ Sort by: date (default), engagement
└─ Graph: engagement over time
```

#### 4. Performance Ranking (per account)
```
Show:
├─ All posts from account X (highest engagement first)
├─ Top 10 posts
├─ Each showing:
│  ├─ Content
│  ├─ Engagement rate
│  ├─ Likes, replies, retweets
│  └─ Posted when
└─ Identifies patterns to watch (will use in Stage 2)
```

#### 5. Account vs Account Comparison
```
Select 2 accounts, show side-by-side:
├─ Follower count
├─ Growth rate
├─ Avg engagement rate
├─ Consistency (variance)
├─ Posts posted
├─ Health score
└─ Table: which is winning on each metric
```

#### 6. Post vs Post Comparison
```
Select 2 posts, show side-by-side:
├─ Content
├─ Posted when
├─ Account
├─ Engagement rate
├─ Likes, replies, retweets
├─ Impressions
├─ Engagement breakdown (% likes vs replies vs retweets)
└─ Which performed better
```

#### 7. Niche Overview
```
Show:
├─ All 5 niches in a table:
│  ├─ Niche name
│  ├─ Accounts in niche (count)
│  ├─ Total followers
│  ├─ Avg engagement rate
│  ├─ Avg growth rate
│  └─ Total posts posted
└─ Graph: engagement by niche over time
```

---

## Part 7: Implementation Order

```
Week 1:
├─ [ ] Set up Accounts collection (5 accounts, minimal config)
├─ [ ] Deploy Posts collection
├─ [ ] Deploy EngagementSnapshot collection
├─ [ ] Deploy AccountMetrics collection
└─ [ ] Create indexes for top queries

Week 2:
├─ [ ] Build ContentCreator agent (simple prompt, random generation)
├─ [ ] Build SafetyGuardian agent (basic checks)
├─ [ ] Build hourly job orchestration
├─ [ ] Test with manual posts (before automation)
└─ [ ] Create Learnings collection (empty, placeholder)

Week 3:
├─ [ ] Start hourly automation (posts every hour on the hour)
├─ [ ] Set up Twitter engagement polling (hourly updates)
├─ [ ] Build AccountMetrics calculation (hourly batch)
├─ [ ] Monitor for bugs/errors
└─ [ ] Verify data is accumulating correctly

Week 4:
├─ [ ] Build Dashboard views (all 7 views above)
├─ [ ] Test dashboard queries
├─ [ ] Manual review of data quality
├─ [ ] Identify any data gaps
└─ [ ] Prepare for Stage 2 pattern discovery script
```

---

## Part 8: Data Expectations (after 4 weeks)

```
By end of Stage 1:

Posts: ~3000 total (5 accounts × 24 hours × 30 days × ~1 post/hour)
EngagementSnapshots: ~33,000 (3000 posts × 11 snapshots)
Accounts: 5 docs
AccountMetrics: ~3,600 (5 accounts × 24 hours × 30 days)
Learnings: 5 placeholder docs (empty, ready for Stage 2)
PatternPerformance: ~3,600 empty or placeholder docs

Expected Data Quality:
├─ Engagement data: Complete for all posts
├─ Post content: All stored with metadata
├─ Account metrics: Hourly snapshots for 14 days (rolling window)
├─ Tones: Not analyzed yet
├─ Patterns: Not discovered yet
└─ Historical record: Complete and searchable
```

---

## Part 9: Success Criteria for Stage 1

✅ All 5 accounts posting reliably every hour (24/7)
✅ <1% posting failure rate
✅ Engagement data capturing for 100% of posts
✅ AccountMetrics calculating correctly
✅ Dashboard queries responding <500ms
✅ No safety guardian rejections (or <10% if rejections enabled)
✅ Data accumulating as expected (~3000 posts + engagement by end)
✅ Historical record complete and searchable
✅ Ready for Stage 2 pattern discovery script

---

## Part 10: Stage 1 -> Stage 2 Transition

**Do NOT do:**
- Delete Stage 1 accounts
- Reset database
- Stop collecting data

**Do:**
- Run pattern discovery script on Stage 1 data
- Back-tag Stage 1 posts with discovered patterns
- Add AccountTonePreferences collection
- Deploy Learnings and PatternPerformance for real use
- Add Stage 2 accounts alongside Stage 1 accounts
- Launch new ContentCreator with pattern + tone logic
- Continue hourly jobs, now with new logic

**Carry Forward:**
- All 5 accounts (keep running)
- All posts and engagement data (full history)
- All AccountMetrics (accumulating)
- All patterns discovered from Stage 1
- Dashboard (update with new views in Stage 2)

---

## Storage & Cost Estimates

**Storage (end of Stage 1):**
- Posts: ~30MB (3000 posts × 10KB)
- EngagementSnapshots: ~100MB (33000 docs × 3KB)
- AccountMetrics: ~36MB (3600 docs × 10KB)
- Total: ~170MB (very manageable)

**Compute:**
- Hourly job: ~30 seconds per run
- Dashboard queries: <500ms each
- Pattern discovery (Stage 2): ~5-10 minutes on Stage 1 data

**Cost (estimate):**
- Twitter API: $0 (free tier)
- Claude API: ~$5-10 (5000 API calls × 1000 tokens × price)
- RavenDB: Free (local instance)
- Total: ~$10/month

---

## Notes for Implementation

- **ContentCreator simplicity:** Just trending topics + prompt, no optimization
- **No tone tracking:** Tones exist in Posts, but we don't analyze or use them yet
- **No pattern use:** Learnings collection exists but is empty/placeholder
- **Focus on stability:** Get reliable posting + data collection working first
- **Dashboard is read-only:** No modifications, just viewing
- **Keep it simple:** The goal is foundation, not optimization
