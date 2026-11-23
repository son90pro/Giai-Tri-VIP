print("Top-level keys:", list(data.keys()))
for idx, prov in enumerate(data.get("providers", [])):
    print(f"Provider #{idx}: keys={list(prov.keys())} | name={prov.get('name')} | id={prov.get('id')} | url={prov.get('url')}")
    
