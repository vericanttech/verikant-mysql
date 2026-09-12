# Vericant Marketing Roadmap

Last updated: 2026-09-12

## Product goal

Help a shop owner understand Vericant quickly, see the product working, and take a measurable next step: request a demo, start a trial, contact sales on WhatsApp, or sign in as an existing customer.

## Now — Redesign the landing page

### 1. Clarify the first screen

- Replace the blocking promotional popup with a clear hero section.
- Use one concrete promise focused on sales, stock, and proof of business activity.
- Separate the primary prospect action (`Demander une démo` or `Essayer gratuitement`) from `Déjà client ? Se connecter`.
- Use a WhatsApp sales action with a prefilled message.
- Label the sales and support telephone numbers clearly and consistently.

### 2. Tell the product story while the visitor scrolls

Build a lightweight sequence of animated product demonstrations:

1. **Create a sale** — products enter a bill and the total updates.
2. **Update stock automatically** — the stock count decreases and a low-stock alert appears.
3. **Understand the business** — the dashboard totals animate into place for sales, expenses, and profit.
4. **Publish a promotion** — a merchant selects products, marks a promo, and previews the public storefront.
5. **Reach customers** — the promotion becomes a WhatsApp share card and a customer opens the storefront.
6. **Work as a team** — show multiple users and shops connected to the same account.

Animations should support the explanation, not decorate it. Use CSS transitions and `IntersectionObserver` where possible, lazy-load media, provide a reduced-motion version, and keep the experience smooth on low-cost mobile phones and slower connections.

### 3. Add conversion and trust sections

- Product screenshots that match the current interface.
- A short “How it works” section.
- Customer testimonials and recognizable merchant logos when permission is available.
- A simple pricing or “contact us for pricing” section.
- Frequently asked questions covering setup, devices, data safety, support, and printing.
- A final WhatsApp/demo call to action.
- Remove fear-based copy such as “you may not need Vericant” and emphasize concrete outcomes.

### 4. Improve sharing, search, and measurement

- Add a meta description, canonical URL, Open Graph image, and social-preview metadata.
- Track demo, WhatsApp, login, contact-form, and install-button clicks.
- Preserve campaign/UTM information when a prospect contacts Vericant.
- Establish a baseline for landing visits and conversion rate before further experiments.

### Landing-page completion criteria

- No automatic modal obscures the first screen.
- A prospect and an existing customer can immediately identify the correct next action.
- The feature story works with touch, keyboard, and reduced-motion settings.
- The page remains useful when JavaScript or animation is unavailable.
- Mobile performance and layout are verified on a narrow viewport and a slower connection.
- Contact submissions and WhatsApp clicks can be attributed to their source.

## Next — Activate merchant storefronts

- Add guided onboarding and bulk product selection for an empty storefront.
- Show a clear preview before publishing.
- Print storefront QR codes only after useful content is published.
- Add an explicit owner-controlled storefront enable/disable setting.
- Add `Commander sur WhatsApp` to each product with a prefilled product message.
- Add friendly public URLs or shop slugs while preserving existing links.
- Give expired promotions a safe automatic end state.
- Validate discount percentages on the server between 0 and 100.

## Later — Build a measurable marketing funnel

- Track storefront source, QR scans, product views, WhatsApp clicks, and enquiries.
- Show top products and conversion signals in the merchant dashboard.
- Generate separate share formats for WhatsApp/feed (`1080×1350`) and Stories/status (`1080×1920`).
- Add direct native sharing from the product list instead of an ambiguous `Image` link.
- Add optional lead capture and follow-up reminders.
- Notify merchants or Vericant staff about meaningful leads without exposing customer credentials.
- Move visit throttling and attribution into a shared database/cache so multiple web workers do not inflate counts.

## Future experiments

- Industry-specific landing pages for boutiques, pharmacies, hardware shops, and wholesalers.
- Referral links for existing merchants.
- Reusable promotional campaign templates.
- Scheduled promotion start/end dates.
- Customer opt-in lists and compliant promotional messaging.
- A/B tests for hero copy, demo offers, and WhatsApp calls to action.

## Important safeguards

- Never include passwords or plaintext usernames in analytics or notifications.
- Obtain permission before displaying customer testimonials, logos, or store information.
- Provide shop owners control over what is publicly visible.
- Add rate limiting and spam protection to public contact and lead forms.
- Have the legal and privacy wording reviewed for the jurisdictions where Vericant operates.

