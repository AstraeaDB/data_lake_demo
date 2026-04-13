# Metadata Graph Schema

## Node Types

### Domain (4 nodes)
Broad categories of business data.
- **Properties:** name, description
- **Embedding:** yes (on description)

### DataSource (8 nodes)
A file or table in the data lake.
- **Properties:** name, description, format, file_path, origin_system, active_from, active_to
- **Embedding:** yes (on description)

### Field (~70 nodes)
A column or field within a data source.
- **Properties:** name, description, data_type, nullable, avro_type, sample_values, source_name
- **Embedding:** yes (on description)

### Concept (~20 nodes)
An abstract business concept that links related fields across sources.
- **Properties:** name, description, domain
- **Embedding:** yes (on description)

## Edge Types

| Edge | From | To | Count | Purpose |
|------|------|----|-------|---------|
| BELONGS_TO_DOMAIN | DataSource | Domain | 8 | Categorization |
| HAS_FIELD | DataSource | Field | ~70 | Source contains this column |
| MAPS_TO_CONCEPT | Field | Concept | ~60 | Field represents this concept |
| SUCCEEDED_BY | DataSource | DataSource | 2 | Temporal succession (platform migration) |
| OVERLAPS_WITH | DataSource | DataSource | 5 | Same time period coverage |
| SAME_ENTITY_AS | Field | Field | ~12 | Same real-world entity across sources |
| RELATES_TO | Concept | Concept | ~5 | Semantic relationship between concepts |

## Identifier Mapping

Different systems use different identifier formats for the same person:

```
U0042 (security) <-- numeric portion --> EMP-0042 (legacy HR)
  |                                          |
  +-- append @acmecorp.com                   +-- crosswalk
  |                                          |
  v                                          v
U0042@acmecorp.com (comms, PM)           WKR-0042 (modern HR)
```

The SAME_ENTITY_AS edges in the graph encode these mappings with transform descriptions.
