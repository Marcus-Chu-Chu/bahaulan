# Dashboard build guide

This guide builds two dashboards from the same pipeline output: one in Tableau Public and one
in Power BI Desktop. Every step is a click path, written for someone who has never opened
either tool.

## The data

The daily run attaches seven files to the `latest` release. Each has a stable URL of the form
`https://github.com/Marcus-Chu-Chu/bahaulan/releases/download/latest/<file>`:

| File | What it holds |
|---|---|
| `dashboard.csv` | 63,270 rows, 21 columns: 1,710 barangays over a 37-day window |
| `dashboard.hyper` | The same rows as a Tableau extract, one table named `dashboard` |
| `dashboard.parquet` | The same rows as Parquet |
| `warnings.csv` | Every forecast hour of the current run, one row per grid point per hour |
| `river.csv` | GloFAS river discharge per grid point per day |
| `monthly_normal.csv` | Monthly NCR rainfall against the 2020 to 2025 normal |
| `metadata.json` | One object describing the run |

`river.csv`, `monthly_normal.csv` and `metadata.json` are also committed under `exports/`, so a
local clone works for those three. The other four live only on the release.

`dashboard.csv` and `dashboard.hyper` carry these columns in this order:

`date`, `source`, `pcode`, `name`, `city`, `population`, `score`, `pct_area_mh_25`,
`est_pop_exposed_25`, `grid_id`, `rain_mm`, `rain_prob_max`, `rain_hours`, `rain_3d_mm`,
`rain_7d_mm`, `wet_exposure`, `max_hourly_mm`, `warning_level`, `run_date`, `lat`, `lon`

`source` is `observed` for ERA5 rows and `forecast` for the rest. `warning_level` is one of
`none`, `yellow`, `orange`, `red`. `docs/data-dictionary.md` defines every column in every
file, with units and the model-versus-gauge caveat.

## Part A: Tableau Public

### 1. Install Tableau Public

Go to `https://www.tableau.com/products/public/download` and click the download button. Run the
installer and accept the defaults. On first launch, create a free Tableau Public account when
prompted, or create one at `https://public.tableau.com`. You need the account at step 9, because
Tableau Public saves workbooks to the web rather than to your disk.

### 2. Connect the data

Download `dashboard.hyper` from the release URL above and put it somewhere you can find again.

In Tableau Public, the start page has a Connect column on the left. Click `More...` under
`To a File`, change the file-type dropdown to `Tableau extract`, pick `dashboard.hyper`, and
click Open. The canvas fills with a table called `dashboard`. If it does not, drag `dashboard`
from the left list onto the canvas.

If you would rather use the CSV, click `Text file` instead and pick `dashboard.csv`.

Now check the types on the Data Source tab. Each column header in the grid has a small icon.

- `date` needs a calendar icon. If it shows `Abc`, click the icon and choose `Date`.
- `lat` and `lon` need `#`. If either shows `Abc`, click the icon and choose `Number (decimal)`.

Click the `Sheet 1` tab at the bottom. In the Data pane on the left, right-click `lat`, choose
`Geographic Role`, then `Latitude`. Right-click `lon`, choose `Geographic Role`, then
`Longitude`.

### 3. Sheet "Exposure map"

Double-click the `Sheet 1` tab and rename it to `Exposure map`.

1. Drag `lon` to the Columns shelf and `lat` to the Rows shelf. Tableau averages both, which is
   what you want once `pcode` is on Detail.
2. On the Marks card, change the dropdown from `Automatic` to `Circle`.
3. Drag `pcode` onto `Detail` on the Marks card. You now have one circle per barangay.
4. Drag `population` onto `Size`. Right-click the new `SUM(population)` pill, choose `Measure`,
   then `Average`. Without this, a barangay that appears on three days gets a circle three times
   too big.
5. Drag `wet_exposure` onto `Color` and set it to `Average` the same way. Click `Color`, then
   `Edit Colors...`, and pick `Orange-Red Sequential` from the palette dropdown.
6. Drag `source` to the Filters shelf, tick `forecast` only, and click OK.
7. Drag `date` to the Filters shelf. Choose `Relative dates`, then `Days`, then `Next`, and set
   the count to 3. Click OK.
8. Drag `name`, `city`, `rain_3d_mm`, `warning_level` and `est_pop_exposed_25` onto `Tooltip`.
   Click `Tooltip` to reword the text if you want.

### 4. Sheet "7-day forecast by city"

Right-click the sheet tab at the bottom, choose `New Worksheet`, and rename it to
`7-day forecast by city`.

1. Drag `date` to Columns. Click the pill's arrow and choose `Day` from the second, green group
   of date options, so the axis is continuous.
2. Drag `rain_mm` to Rows, then set the pill to `Average` through its right-click menu.
3. Drag `warning_level` onto `Color`. Click `Color`, then `Edit Colors...`, and assign grey to
   `none`, yellow to `yellow`, orange to `orange` and red to `red`.
4. Drag `source` to Filters and keep `forecast`.
5. Drag `city` to Filters, click `All`, then OK. Right-click the `city` pill on the Filters
   shelf and choose `Show Filter`, so the control appears on the right.
6. Open the `Analytics` pane, the tab next to `Data` at the top left. Drag `Reference Line` onto
   the view and drop it on `Table`. Choose `Constant`, type `7.5`, set Label to `None`, and click
   OK. Repeat for `15` and `30`.

Those three numbers are the PAGASA hourly bands: yellow at 7.5 mm in an hour, orange at 15, red
at 30. The bars are daily totals in mm, so a bar crossing 30 does not mean a red hour happened.
The `warning_level` color carries the real band, because it comes from `max_hourly_mm`. If you
want the lines to mark an actual threshold, swap `AVG(rain_mm)` on Rows for `MAX(max_hourly_mm)`.
The axis then reads in mm per hour, and a bar crossing 15 is an orange hour.

### 5. Sheet "12-month observed vs normal"

Add `monthly_normal.csv` as a second data source. Use the `Data` menu, then `New Data Source`,
then `Text file`, and pick the file from your clone's `exports/` folder or from the release.

Make a new worksheet and rename it `12-month observed vs normal`.

1. With the `monthly_normal` source selected at the top of the Data pane, drag `month_start` to
   Columns and set the pill to `Month` in the green group.
2. Drag `total_mm` to Rows.
3. Drag `normal_mm` to Rows, to the right of `total_mm`. You now have two stacked charts.
   Right-click the `normal_mm` axis, choose `Dual Axis`, then right-click either axis and choose
   `Synchronize Axis`.
4. On both Marks cards, set the mark type to `Line`.
5. Drag `year` to Filters and keep the last two years.
6. Drag `is_complete` to Filters and keep `True`. The current month is partial until ERA5 catches
   up, and leaving it in makes this year look drier than it is.
7. Optional band: drag `p10_mm` and `p90_mm` to Rows, set their mark type to `Area`, and push
   them behind the lines with `Move Marks to Back` from the axis right-click menu.

### 6. Sheet "River discharge"

Add `river.csv` as a third data source the same way. New worksheet, renamed `River discharge`.

1. Drag `date` to Columns and set it to `Day` in the green group.
2. Drag `river_discharge` to Rows and set the pill to `Average`.
3. Drag `grid_id` onto `Color`.
4. Drag `cities_served` onto `Tooltip`.
5. Thirty-one lines is unreadable. Drag `grid_id` to Filters as well and keep three or four
   points, whichever ones have the cities you care about in `cities_served`.

### 7. Sheet "Freshness"

New worksheet, renamed `Freshness`.

Try the JSON connector first: `Data`, then `New Data Source`, then `More...`, then `JSON file`,
and pick `exports/metadata.json`. Tableau asks which schema levels to include. Tick all of them
and click OK. Set the mark type to `Text`, then drag `run_date`, `latest_observed_date`,
`forecast_through`, `active_grid_points` and `dashboard_rows` onto `Text` on the Marks card, one
at a time.

If your build does not offer `JSON file`, type the five values in by hand instead. On the
dashboard in step 8, drag a `Text` object from the Objects list into the layout and type them.
Open `exports/metadata.json` in a text editor to read them, and update the text whenever you
republish.

### 8. Assemble the dashboard

Click the `New Dashboard` icon at the bottom, the middle of the three icons next to the sheet
tabs.

1. In the Size dropdown on the left, choose `Custom size` and enter `1200` by `900`.
2. At the bottom of the left panel, switch from `Floating` to `Tiled`.
3. Drag `Exposure map` onto the canvas. It fills the whole area. Drag its right edge left until
   it takes about 60 percent of the width.
4. Drag `7-day forecast by city` into the empty area on the right, at the top.
5. Drag `12-month observed vs normal` below it, still on the right.
6. Drag `River discharge` onto the bottom edge so it spans the full width, then drop `Freshness`
   to its right.
7. Click the `city` filter card, open its arrow menu, choose `Apply to Worksheets`, then
   `All Using This Data Source`.
8. Tick `Show dashboard title` at the bottom left, then double-click the title and type
   `BahaUlan: Metro Manila rain, river and flood exposure`.
9. Drag a `Text` object under the title and paste this caption:

   > Rainfall and discharge are model output, not gauge readings. Forecasts from Open-Meteo,
   > past rainfall from ERA5, river discharge from GloFAS, under the Open-Meteo CC BY 4.0 terms
   > and the Copernicus terms. Exposure score, hazard share and exposed population from BahaMap.

### 9. Publish

Use `File`, then `Save to Tableau Public As...`. Sign in when asked. Name the workbook `BahaUlan`
and click Save. Tableau opens the published workbook in your browser once it finishes.

Copy the browser URL. Paste it into the Dashboard section of `README.md`, replacing the line that
says the workbook is not published yet.

Back in Tableau, use `Dashboard`, then `Export Image...`, and save the PNG as
`dashboards/screenshots/overview.png` in your clone. Commit the README change and the screenshot.

## Part B: Power BI Desktop

Power BI Desktop is a Windows application. If it is not installed, get it from the Microsoft
Store or from `https://powerbi.microsoft.com/desktop/`.

### 1. Load the four tables

Point Power BI at the release URLs rather than at local files, so `Refresh` picks up each new
daily run.

1. On the Home ribbon, click `Get data`, then `Web`.
2. Leave `Basic` selected and paste
   `https://github.com/Marcus-Chu-Chu/bahaulan/releases/download/latest/dashboard.csv`. Click OK.
   If Power BI asks how to authenticate, choose `Anonymous` and click Connect.
3. A preview window opens. Click `Transform Data` to open Power Query.
4. If the first row of data is sitting in the header, click `Use First Row as Headers` on the
   Home ribbon.
5. Click the type icon to the left of the `date` column name and choose `Date`. Do the same for
   `lat` and `lon`, choosing `Decimal Number`. Use `Decimal Number` as well for `rain_mm`,
   `rain_3d_mm`, `rain_7d_mm`, `wet_exposure` and `max_hourly_mm` if they came in as text.
6. Rename the query to `dashboard` in the Properties box on the right.
7. Repeat steps 1 through 6 for `monthly_normal.csv`, `river.csv` and `warnings.csv`. Use `Home`,
   then `New Source`, then `Web` while Power Query is open.
8. Click `Close & Apply`.

Local alternative: `Get data`, then `Text/CSV`, and pick the file from your clone. That loads
faster and works offline. `Refresh` then rereads the file on disk, so you have to download a new
copy yourself after each run.

### 2. Check the model

Click the Model view icon, third in the left rail. Power BI may have guessed relationships.
Delete any it invented between `dashboard` and `warnings`.

The one relationship worth keeping is `dashboard[date]` to `river[date]`, if you want the `city`
slicer to move the river chart too. Drag `date` from `dashboard` onto `date` in `river`, set
Cardinality to `Many to many`, and set Cross filter direction to `Single`.

Skip this step if you are happy for the river chart to ignore the slicer.

### 3. Build the visuals

Click the Report view icon, first in the left rail. Each visual below starts by clicking its icon
in the Visualizations pane on the right, then dragging fields from the Data pane into the wells
underneath.

Map: pick the `Map` visual. Drag `lat` into `Latitude` and `lon` into `Longitude`, and set both
to `Don't summarize` through the field's arrow menu. Drag `pcode` into `Location` and
`population` into `Bubble size`, set to `Average`. Drag `wet_exposure` into `Tooltips` so it
reads on hover, and set the bubble color in the `Format` pane under `Bubbles`.

Rainfall bars: pick `Clustered column chart`. Drag `date` into `X-axis`, then use the field's
arrow menu to pick `date` rather than `Date Hierarchy`. Drag `rain_mm` into `Y-axis` and set it
to `Average`. Drag `warning_level` into `Legend`. Open the `Analytics` pane, the magnifying-glass
icon under Visualizations, add three `Constant line` entries, and set them to `7.5`, `15` and
`30`. The caveat from Part A step 4 applies here too.

Monthly line: pick `Line chart`. Drag `month_start` into `X-axis`, then `total_mm` and
`normal_mm` into `Y-axis`. Add `is_complete` to the `Filters on this visual` pane and keep
`True`.

River line: pick `Line chart`. Drag `date` into `X-axis`, `river_discharge` into `Y-axis` set to
`Average`, and `grid_id` into `Legend`. Filter `grid_id` down to three or four points.

Freshness cards: `Get data`, then `Web`, and paste
`https://github.com/Marcus-Chu-Chu/bahaulan/releases/download/latest/metadata.json`. Power Query
opens it as a record. Click `Into Table` on the `Convert` ribbon, then use the expand arrow on
the value column. Close & Apply, then add one `Card` visual each for `run_date`,
`latest_observed_date`, `forecast_through` and `active_grid_points`.

### 4. Slicer and page size

Click a blank part of the canvas, pick the `Slicer` visual, and drag `city` into `Field`. Leave
it as a list, or switch it to a dropdown in the `Format` pane under `Slicer settings`.

Open the `Format` pane with nothing selected, choose `Canvas settings`, set `Type` to `Custom`,
and enter `1280` by `720`.

Leave the theme on the default. `View`, then `Themes`, has others if you want one.

### 5. Save and commit

Use `File`, then `Save as`, and save to `dashboards/bahaulan.pbix` in your clone.

Take a screenshot of the report page and save it as `dashboards/screenshots/powerbi.png`.

Commit both. The `.pbix` runs 2 to 5 MB. Committing it once is fine, and updates are worth
committing rarely, because git stores a whole new copy of the file each time.

## How each tool sees new data

The pipeline runs at 22:00 UTC daily, which is 06:00 in Manila, and replaces the files on the
`latest` release.

Power BI Desktop picks up the new run when you click `Refresh` on the Home ribbon, as long as the
queries point at the release URLs from Part B step 1.

Tableau Public holds whatever extract you uploaded. To move it forward, open the workbook in
Tableau Public Desktop, connect it to a freshly downloaded `dashboard.hyper`, and use
`Save to Tableau Public` again. The published URL stays the same.
