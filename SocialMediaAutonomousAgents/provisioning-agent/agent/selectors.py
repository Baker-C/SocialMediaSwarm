"""Centralized selectors and visible-text signals for the X signup/dev flow.

============================================================================
PLACEHOLDER VALUES — NEED THE SPIKE (docs/plans/x-account-provisioning/09 §1)
============================================================================
Every CSS selector and text token below is a GUESS. X ships a single reactive
signup flow with obfuscated, frequently-changing markup. The REAL values MUST be
captured from a manual DOM spike before the agent can drive the live flow.

This is THE single file to edit when X changes its DOM. Keep all selector/text
knowledge here; the detector and handlers reference `SEL` / `TXT` only.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Selectors:
    # --- overlay / captcha (checked first; can cover any page) ---
    captcha_iframe: str = 'iframe[title*="arkose" i], iframe[src*="arkoselabs" i]'  # PLACEHOLDER

    # --- generic "next"/"submit" advance button ---
    next_button: str = '[data-testid="ocfEnterTextNextButton"], [role="button"]:has-text("Next")'  # PLACEHOLDER

    # --- email entry ---
    email_input: str = 'input[name="email"], input[autocomplete="email"]'  # PLACEHOLDER

    # --- password ---
    password_input: str = 'input[name="password"], input[type="password"]'  # PLACEHOLDER

    # --- name + handle ---
    name_input: str = 'input[name="name"], input[autocomplete="name"]'  # PLACEHOLDER
    handle_input: str = 'input[name="username"], input[autocomplete="username"]'  # PLACEHOLDER
    handle_taken_error: str = '[data-testid="username-error"], [role="alert"]'  # PLACEHOLDER

    # --- email verification code ---
    email_code_input: str = 'input[name="verfication_code"], input[autocomplete="one-time-code"]'  # PLACEHOLDER

    # --- phone entry ---
    phone_input: str = 'input[name="phone_number"], input[autocomplete="tel"]'  # PLACEHOLDER

    # --- phone verification code ---
    phone_code_input: str = 'input[name="verfication_code"]'  # PLACEHOLDER

    # --- profile setup ---
    avatar_input: str = 'input[type="file"][data-testid="avatar"]'  # PLACEHOLDER
    header_input: str = 'input[type="file"][data-testid="header"]'  # PLACEHOLDER
    bio_input: str = 'textarea[name="bio"], textarea[data-testid="bio"]'  # PLACEHOLDER
    profile_save_button: str = '[data-testid="profileSave"]'  # PLACEHOLDER

    # --- developer app creation ---
    dev_app_name_input: str = 'input[name="app_name"]'  # PLACEHOLDER
    dev_app_create_button: str = '[data-testid="createApp"]'  # PLACEHOLDER
    dev_app_root: str = '[data-testid="devAppForm"]'  # PLACEHOLDER

    # --- developer agreement ---
    dev_agreement_checkbox: str = 'input[type="checkbox"][name="agreement"]'  # PLACEHOLDER
    dev_agreement_accept_button: str = '[data-testid="acceptAgreement"]'  # PLACEHOLDER
    dev_agreement_root: str = '[data-testid="devAgreement"]'  # PLACEHOLDER

    # --- billing ---
    card_number_input: str = 'input[name="cardnumber"], input[autocomplete="cc-number"]'  # PLACEHOLDER
    card_exp_input: str = 'input[name="exp-date"], input[autocomplete="cc-exp"]'  # PLACEHOLDER
    card_cvv_input: str = 'input[name="cvc"], input[autocomplete="cc-csc"]'  # PLACEHOLDER
    card_name_input: str = 'input[autocomplete="cc-name"]'  # PLACEHOLDER
    billing_submit_button: str = '[data-testid="billingSubmit"]'  # PLACEHOLDER
    billing_root: str = '[data-testid="billingForm"]'  # PLACEHOLDER

    # --- API key capture ---
    api_key_value: str = '[data-testid="apiKey"]'  # PLACEHOLDER
    api_secret_value: str = '[data-testid="apiSecret"]'  # PLACEHOLDER
    bearer_token_value: str = '[data-testid="bearerToken"]'  # PLACEHOLDER
    x_user_id_value: str = '[data-testid="userId"]'  # PLACEHOLDER
    dev_app_id_value: str = '[data-testid="appId"]'  # PLACEHOLDER

    # --- success ---
    success_marker: str = '[data-testid="provisioningSuccess"]'  # PLACEHOLDER


@dataclass(frozen=True)
class TextSignals:
    """Visible-text tokens (lowercased substring match against the page body)."""

    captcha: str = "arkose"  # PLACEHOLDER
    success: str = "you're all set"  # PLACEHOLDER


SEL = Selectors()
TXT = TextSignals()

# Body selector used for whole-page text scans (CAPTCHA/success token checks).
BODY = "body"
