# Solar Setu Project Notes

## 1. Project Overview

Solar Setu is a rooftop solar estimation and decision-support web application.

It allows users to:

- Analyze rooftop suitability.
- Estimate the recommended solar system size.
- Calculate annual solar generation.
- Estimate system cost, subsidy and savings.
- Calculate payback period.
- Compare solar providers.
- Ask Surya AI questions about the analysis.
- View reports and download PDF reports.

---

## 2. Main Technologies

### Backend

- Python
- Flask web framework
- SQLAlchemy ORM
- Flask-Migrate and Alembic for database migrations
- Requests for external API calls
- pvlib for solar/PV calculations
- WeasyPrint and ReportLab for PDF reports

### Frontend

- HTML templates using Jinja2
- CSS
- Vanilla JavaScript
- Chart.js for report visualizations
- JavaScript files:
  - `main.js`
  - `compare.js`
  - `map.js`
  - `surya.js`

### AI

- Surya AI uses an external AI provider.
- Gemini or an OpenAI-compatible provider can be configured.
- API keys are stored in environment variables and should not be committed to source code.

---

## 3. Database

The application supports two database systems.

### SQLite

SQLite is the default database for local development.

```text
solar_app.db
```

It is simple to use and does not require a separate database server.

### PostgreSQL

PostgreSQL is supported for production deployments.

The database connection is configured through:

```text
DATABASE_URL
```

The same application can therefore use SQLite locally and PostgreSQL in production.

### Main Tables

#### `user_locations`

Stores each rooftop analysis, including:

- Address and coordinates
- Rooftop polygon
- Obstructions
- Roof and usable roof area
- Recommended system size
- Annual generation
- System cost
- Subsidy
- Net investment
- Monthly savings
- Battery and inverter details
- Payback period
- Environmental impact
- Additional calculation values

#### `users`

Stores optional user account information.

#### `solar_providers`

Stores solar provider/company information.

#### `solar_solutions`

Stores provider-specific package and equipment information, such as:

- Panel brand and model
- Panel type
- Panel efficiency
- Inverter details
- Warranties
- Indicative price range
- Installation availability
- Financing availability

#### `saved_comparisons`

Stores comparisons saved by registered users.

#### `tariff_table`

Stores electricity tariff reference data.

#### `subsidy_scheme`

Stores solar subsidy rules.

---

## 4. Initial Version

The initial website mainly provided a basic rooftop solar estimation flow.

The user could:

1. Enter or select a location.
2. Define a rooftop area.
3. Run an analysis.
4. View solar results.

The provider comparison feature existed, but the comparison cards relied too heavily on fixed provider catalogue values.

This meant that values such as provider system size and pricing could remain unchanged after the user created a new analysis.

---

## 5. Main Problem Found

The Compare page did not always represent the user's latest Solar Setu analysis.

The user could change:

- Roof area
- Electricity bill or consumption
- System size
- Location
- Roof obstructions
- Panel type
- Battery selection
- Inverter selection
- Other analysis inputs

However, the Compare page could still show old or default values.

### Root Cause

The provider catalogue contained fixed system sizes and fixed price ranges.

The comparison logic used the current analysis mainly for match scoring, but the comparison serializer returned catalogue values directly for important card fields.

As a result:

- System size could remain static.
- Price could remain static.
- Comparison cards did not fully reflect the latest analysis.

---

## 6. Current Analysis Flow

```text
User Inputs
    -> Solar Estimation Logic
    -> UserLocation Database Record
    -> Report / Savings / Compare / PDF
    -> Surya AI Context
```

When the user runs an analysis, the backend calculates the result and stores it as a new `UserLocation` record.

The saved record is then used by:

- Report page
- Savings page
- Compare page
- PDF report
- Surya AI

This makes the stored analysis the central source of truth.

---

## 7. Solar Calculation Features

The current system considers:

- Total roof area
- Obstructed area
- Usable roof area
- Roof capacity
- Location
- Orientation
- Solar irradiance
- Electricity tariff
- Monthly electricity bill
- Property type
- Battery size
- Backup requirements
- Inverter preference

### Calculated Results

The application calculates:

- Recommended system size
- Annual generation
- Monthly generation
- System cost
- Low and high cost estimates
- Subsidy
- Battery cost
- Net investment
- Monthly savings
- Annual savings
- Payback period
- Operations and maintenance estimate
- Lifetime generation
- LCOE
- CO2 reduction
- Environmental equivalents

---

## 8. Important Compare Page Fix

The main fix was made in:

```text
app/services/compare_service.py
```

Previously, the comparison serializer received only the recommended system size for scoring.

It now receives the complete current analysis:

```python
serialize_solution(solution, analysis, priority, price_bounds)
```

The comparison cards are now calculated from the latest saved analysis.

### Values That Update

These values update when the analysis changes:

- System size
- Annual generation
- Annual savings
- Estimated price
- Payback period
- Number of panels

### Provider Differences That Remain

The application still preserves legitimate provider-specific differences:

- Provider name
- Panel brand
- Panel model
- Panel type
- Panel efficiency
- Inverter brand
- Inverter model
- Inverter type
- Panel warranty
- Performance warranty
- Inverter warranty
- Installation availability
- Financing availability
- Regional availability
- Price range

The current analysis provides the base calculation, while the provider catalogue supplies company-specific information.

---

## 9. Provider Price Calculation

Provider catalogue prices are based on catalogue system sizes.

The current comparison logic scales these prices to the user's current system size.

Conceptually:

```text
Current provider price =
Catalogue price x Current system size / Catalogue system size
```

Current battery cost is also included when applicable.

This approach is deterministic and does not use random values.

Prices remain indicative because actual prices depend on:

- Site survey
- Installation conditions
- Equipment selection
- Location
- Incentives
- Final provider quotation

---

## 10. Payback Calculation in Compare

The comparison payback uses:

- Current provider-adjusted price
- Current subsidy
- Current annual savings

Conceptually:

```text
Payback =
Provider-adjusted price - Current subsidy
------------------------------------------
Current annual savings
```

Therefore, payback changes when the user's analysis changes.

---

## 11. Latest Analysis Selection

When `/compare` is opened without a specific report ID:

1. The application finds the user's available reports.
2. Reports are ordered by creation time.
3. The newest report is selected.
4. Comparison values are calculated from that report.

When a specific location ID is provided:

```text
/compare?location_id=<id>
```

the selected authorized report is used.

This prevents the Compare page from automatically using an old report.

---

## 12. No Stale Frontend Cache

The comparison values are not loaded from:

- `localStorage`
- `sessionStorage`
- A static JavaScript result object
- A hardcoded frontend comparison result

The provider catalogue is stored in the database, but analysis-dependent values are generated by the backend for the current analysis.

The frontend receives the generated data through:

```javascript
window.COMPARE_SOLUTIONS
```

---

## 13. Compare API

The application provides:

```text
GET /api/compare/<location_id>
```

The endpoint returns:

- Current location analysis
- Current comparison solutions
- Selected comparison priority

It uses the same comparison logic as the Compare page.

---

## 14. Sorting, Ranking and Deduplication

The existing comparison features were preserved.

### Sorting Options

- Recommended
- Lowest estimated cost
- Highest efficiency
- Best warranty
- Best match

### Match Score Factors

The ranking considers:

- System-size fit
- Price
- Panel efficiency
- Warranty
- User priority
- Regional availability

### Provider Deduplication

Duplicate providers are removed using a normalized provider name.

Provider names are converted to lowercase and special characters are removed before comparison.

---

## 15. Surya AI

Surya AI receives the current Solar Setu analysis context.

The context can contain:

- Location
- Roof area
- Usable roof area
- System size
- Annual generation
- Monthly savings
- Annual savings
- Payback period
- Battery size
- Inverter information
- CO2 reduction
- LCOE
- Selected comparison providers

Surya is expected to:

- Use the supplied Solar Setu values.
- Explain the current analysis.
- Explain provider trade-offs.
- Avoid inventing missing values.
- Report unavailable values as unavailable.

---

## 16. Reports and PDF

The current application provides:

- Detailed report page
- Savings dashboard
- Financial results
- Environmental impact
- Charts
- PDF report generation

Reports are generated from saved analysis data rather than temporary frontend values.

---

## 17. Guest and Account Features

### Guest Users

Guest analyses are tracked through session-linked report IDs.

### Registered Users

Registered users can:

- Save reports
- View report history
- Save comparisons
- View saved comparisons
- Manage solar preferences

---

## 18. Important Files

### Backend

```text
app/routes.py
```

Contains page routes, API routes, report handling, comparison handling and Surya endpoints.

```text
app/solar_logic.py
```

Contains rooftop, sizing, generation, financial, subsidy, battery and inverter calculations.

```text
app/models.py
```

Contains database models and provider/reference seed data.

```text
app/services/compare_service.py
```

Contains comparison serialization, provider scoring, regional availability, ranking and current-analysis calculations.

```text
app/services/solar_assistant.py
```

Contains Surya AI integration and context handling.

### Frontend

```text
app/templates/compare.html
```

Contains the Compare page structure.

```text
app/static/js/compare.js
```

Contains filtering, sorting, provider selection, side-by-side comparison, saving and Surya comparison context.

```text
app/static/js/surya.js
```

Contains Surya chat behavior.

```text
app/static/css/style.css
```

Contains the website and Compare page styling.

---

## 19. Initial Version vs Current Version

| Area | Initial Version | Current Version |
|---|---|---|
| Rooftop analysis | Basic estimation flow | Detailed rooftop, obstruction, orientation and energy analysis |
| Data storage | Limited analysis persistence | Saved `UserLocation` analysis records |
| System sizing | Basic result | Roof and bill-based sizing with constraints |
| Financial results | Limited | Cost, subsidy, savings, payback, LCOE and lifetime generation |
| Comparison | Provider catalogue values could remain static | Values recalculate from the current analysis |
| Provider differences | Catalogue information | Provider-specific data is preserved and combined with current analysis |
| Duplicate providers | Could appear more than once | Deduplicated provider list |
| Ranking | Basic comparison | Deterministic match scoring and sorting |
| Reports | Basic result display | Reports, savings dashboard and PDF generation |
| AI | Basic assistant context | Current analysis and provider comparison context |
| Database | Local database usage | SQLite locally with PostgreSQL production support |
| User features | Basic guest flow | Guest history, accounts and saved comparisons |

---

## 20. Validation Performed

The following checks were completed:

- Python compilation passed.
- The comparison serializer was tested with multiple stored analyses.
- Different analyses produced different system sizes and generation values.
- `/compare` returned successfully.
- `/api/compare/<location_id>` returned successfully.
- Provider names remained unique.
- Provider prices remained different.
- Panel counts changed according to the current system size.
- Surya context remained available.
- The local Flask server started successfully.
- The Compare page rendered successfully.

A JavaScript syntax check using Node.js was not available because Node.js was not installed in the environment.

---

## 21. Final Summary

Solar Setu evolved from a basic rooftop estimator into a persistent solar decision-support platform.

The most important functional improvement is that the Compare page now represents the user's latest analysis.

The current implementation:

- Uses the latest saved analysis.
- Recalculates analysis-dependent comparison values.
- Preserves legitimate provider differences.
- Does not use random values.
- Does not rely on stale comparison cache data.
- Keeps sorting, ranking and deduplication.
- Keeps Surya AI connected to the current analysis.
- Supports reports, savings, PDF generation, accounts and saved comparisons.
