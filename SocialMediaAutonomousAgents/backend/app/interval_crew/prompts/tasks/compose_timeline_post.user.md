Account niche: {niche}

Account personality (voice and character — follow closely):
{account_personality}

Posting instructions (how this account writes — structure, format, length-feel):
{account_system_prompt}

Voice guidance — patterns to avoid and patterns to lean into:
{negative_semantics_block}

Reference analysis (patterns from top external + own posts — nudge voice, not topic):
{reference_context_block}

Source post (id={tweet_id}, popularity_score={popularity_score}):
{source_text}

Character limit (required):
- Your post must be at most {body_char_budget} characters.
- A media URL is appended after your text by the app: {append_url}. Its length is already reserved in the limit above, so do not include any URL in your output.

Rewrite for posting. JSON only: {{"post": "..."}}
