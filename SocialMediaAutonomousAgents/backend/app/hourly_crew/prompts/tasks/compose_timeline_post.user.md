Account niche: {niche}

Account personality (voice for the opinion section — follow closely; energetic, emotional, loose grammar, not AI):
{account_personality}

Post structure and formatting rules:
{account_system_prompt}

Banned semantics, phrases, characters, and sentence structures (never use in opinion or quip):
{negative_semantics_block}

Source tweet (id={tweet_id}, popularity_score={popularity_score}):
{source_text}

Character limits (required — the app appends the media URL after your text):
- Full published post maximum: {max_post_len} characters total.
- Media URL appended at end uses {link_char_count} characters (including spacing): {append_url}
- Your opinion + blank line + quip must be at most {text_block_budget} characters combined (excluding the URL).
- Opinion maximum: {opinion_char_max} characters.
- Quip maximum: {quip_char_max} characters.

Rewrite for posting. JSON only.
