# Database Cleanup Documentation

## Output files

For each input CSV, the script creates three output files.

### 1. Cleaned file

`<name>_cleaned.csv`

This is the complete original dataset after automatic cleaning.

All original columns are preserved.

### 2. Changes file

`<name>_changes.csv`

This contains one row per input record.

Columns:

- `ID de registro`
- `email`
- `new address`
- `old address`
- `new city`
- `old city`
- `new province`
- `old province`
- `new country`
- `old country`
- `new postal code`
- `old postal code`
- `change details`

The geographic values themselves are preserved in their original
language. For example, Spanish city, province, country, and address
values remain Spanish.

The explanations in `change details` are written in English.

Every input record is included, including records where no changes
were necessary.

### 3. Review file

`<name>_review.csv`

This contains only values that require manual review.

Examples include:

- postal/province mismatches
- unknown postal prefixes
- suspicious city values
- possible addresses stored in the city field
- possible encoding problems
- invalid postal code formats

## Cleaning rules

### Provinces

Province values are checked against:

`config/provinces.txt`

Configured corrections are read from:

`config/provinces_rules.csv`

The script can apply:

- explicit correction rules
- encoding repair
- capitalization/accent normalization
- conservative fuzzy matching

### Countries

Country values are checked against:

`config/countries.txt`

Configured corrections are read from:

`config/countries_rules.csv`

### Cities

Cities are treated as free text.

The script does not require cities to exist in a closed official list.

It applies conservative:

- encoding repair
- whitespace cleanup
- capitalization

Suspicious values are sent to the review file rather than being
automatically replaced.

### Addresses

Addresses are cleaned using:

- encoding repair
- whitespace cleanup
- capitalization

The script does not attempt to verify whether an address physically
exists.

### Postal codes

Spanish postal codes are expected to contain five digits.

The first two digits are checked against:

`config/spanish_postal_prefixes.csv`

If the postal code conflicts with the province, the values are not
automatically changed. The record is placed in the review file.

## Output language

The actual geographic data is not translated.

For example:

`València`

remains:

`València`

The script's explanations, report headers, review reasons, console
messages, and documentation are written in English, except for the
specific requested geographic column name:

`ID de registro`
