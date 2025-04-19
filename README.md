# Forex Bot

```python
for t, tf in timeframes.items():
    try:
        filepath = pathlib.Path(f"rates/{symbol}/TIMEFRAME_{t}.csv")
        contents.append(
            types.Part.from_bytes(
        data=filepath.read_bytes(),
        mime_type="text/csv",
            )
        )
    except FileNotFoundError as e:
        logger.error(e)
```