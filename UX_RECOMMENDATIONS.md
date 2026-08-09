# mygov UI/UX Recommendations

Reviewed against the current `main` branch and the live deployment at [mygov.faizalmzain.com](https://mygov.faizalmzain.com/).

## Overall assessment

The visual foundation is strong, but the product currently feels more like a technical data dashboard than a friendly public utility. The biggest opportunities are improving perceived speed, personalization, plain-language guidance, and accessibility.

## What is already working well

- Consistent dark visual system, spacing, cards, charts, and sticky navigation.
- Loading skeletons, retry states, offline/PWA support, reduced-motion handling, and skip navigation.
- Useful interactions: weather search/sort, date ranges, CPI filters, route limits, and location selection.
- Strong privacy posture: location is user-triggered, there is no tracking, and data is cached locally.

## Priority recommendations

### 1. Make the first screen personal and actionable

Replace “Malaysia, by the numbers” with a more user-oriented message such as:

> **Today in Malaysia**  
> Weather, fuel prices, warnings, and transport updates for your area.

Add a prominent location selector:

- Use my location
- Choose a district
- Remember the user’s choice
- Show the selected area prominently

Make the top KPI cards clickable. For example:

- “6 warnings” → scroll to warnings
- “RON95 RM3.77” → open Fuel
- “0 vehicles live” → open Live Vehicles

The KPI cards are currently decorative `<div>` elements in [`public/index.html`](public/index.html#L1412).

### 2. Improve the first-load experience

The live page can take roughly half a minute to fully populate because all five sections are loaded sequentially. This is controlled by [`loadAll()`](public/index.html#L1513).

Recommended approach:

- Render cached data immediately.
- Load Weather and Fuel first.
- Lazy-load Economy, Transport, and Live as they approach the viewport.
- Keep existing content visible during refresh instead of replacing it with skeletons.
- Show progress per section: “Weather updated”, “Fuel loading”, etc.
- Display source freshness separately from cache freshness.

This would make the app feel fast even when the API is slow.

### 3. Hide technical details from normal users

The current descriptions expose terms such as GTFS Static, protobuf, endpoint paths, and “inflated in your browser”. These are useful for developers but distracting for the general public.

Move the `GET /...` badges and technical explanations into a collapsed **Data source and methodology** panel.

Prefer simpler copy:

- Scheduled public transport routes
- Live vehicles currently reporting their position
- Household income over time
- Prices are updated weekly

### 4. Fix accessibility issues in the weather table

Weather rows are clickable through mouse events only. This is implemented in [`paintWxRows()`](public/index.html#L1028).

Better options:

- Put a real `<button>` in the first cell.
- Or add keyboard handling, `tabindex="0"`, and an appropriate row role.
- Add a visible focus state.
- Announce location changes with `aria-live="polite"`.

Charts should also have a **View data table** option because tooltips alone are not accessible or discoverable.

### 5. Prioritize weather warnings

The warning block currently presents every notice in the same grid, including “No Advisory” messages. See [`renderWeather()`](public/index.html#L991).

Improve it by:

- Showing active warnings first.
- Highlighting warnings affecting the selected user location.
- Adding severity labels.
- Collapsing all-clear notices under “Other notices”.
- Adding filters such as “My area”, “All Malaysia”, and “Marine”.
- Providing a short summary, such as “Thunderstorms expected in Selangor until 7:00 PM.”

### 6. Make Transport more useful to ordinary people

The Transport and Live sections are data-rich but not very task-oriented. Raw latitude, longitude, route IDs, and protobuf terminology are not useful to most visitors.

Consider adding:

- Route search.
- Stop search.
- Nearest stops using location permission.
- A map view for live vehicles.
- Route filters for KTMB, Rapid KL, bus, and train.
- “Last seen 2 minutes ago” instead of only feed timestamps.
- Mobile-friendly vehicle cards instead of wide tables.

When no vehicles are reporting, show context such as “No live vehicles detected” and the last feed update time.

### 7. Add bilingual support

The interface is English, but forecast data displays Malay phrases such as “Tiada hujan” and “Ribut petir”. A simple English/Bahasa Melayu toggle would make the app more approachable for Malaysian users.

At minimum:

- Translate system labels and empty states.
- Keep original source text available.
- Save the language preference locally.

### 8. Improve contrast and touch targets

The muted `--fg-3` color is used heavily for labels, subtitles, table headings, and navigation in the design system. Some small text may be too low-contrast on dark surfaces; see [`public/index.html`](public/index.html#L121).

Also increase compact controls such as segmented buttons and chips to approximately 40–44px height on mobile. Current controls are visually neat but small for touch interaction.

### 9. Reconsider the dark-only theme

The dark theme is attractive, but a general government-data audience may benefit from:

- Light theme.
- System theme setting.
- Theme toggle.
- Larger text mode.
- Persisted preferences.

The page currently forces dark mode through `color-scheme: dark`.

## Suggested implementation order

1. Faster, progressive loading.
2. Personalized “Today in my area” homepage.
3. Plain-language content and hidden technical details.
4. Keyboard-accessible weather selection and accessible chart alternatives.
5. Warning prioritization.
6. Transport map/search experience.
7. Bilingual and light-theme support.

## Recommended first milestone

Start with a focused v2 UX pass in [`public/index.html`](public/index.html):

1. Redesign the hero and KPI area.
2. Refactor loading to be progressive and preserve existing content during refresh.
3. Fix weather-table keyboard accessibility.
4. Add per-section freshness and clearer warning summaries.

These changes should deliver the largest improvement for general users before adding more datasets or advanced transport features.
