from utils import send_json_response
import json
import re
def build_collection_response(collection, base_url):
    print(collection['extent_period'])

    cleaned = re.findall(r"[-+]?\d*\.\d+|\d+", str(collection['extent']))

    # convert to float
    bbox= list(map(float, cleaned))
    return {
        "id": collection['id'],
        "title": collection['title'],
        "description": collection['description'],
        "itemType": collection['item_type'],
        "updateFrequency": collection['update_frequency'],
        "extent": None if collection['extent'] is None else {
            "spatial": {
                "bbox": bbox[:4],
                # "crs": "http://www.opengis.net/def/crs/OGC/1.3/CRS84"
                "crs": collection['crs']
            },
            "temporal": {
                "interval": str(collection['extent_period']).strip('[]').split(', '),
            # "trs": "http://www.opengis.net/def/uom/ISO-8601/0/Gregorian"
            "trs": collection['trs']
            }
        },
 
        "links": [
            {
                "href": f"{base_url}/collections/{collection['id']}",
                "rel": "self",
                "type": "application/json"
            },
            # {
            #     "href": f"{base_url}/collections/{collection['id']}/items", #ogc yaml mentions HTML if there is one 
            #     "rel": "items",
            #     "type": "application/json"
            # }
        ]
    }


def build_collections_list_response(collections, base_url):
    return {
        "collections": collections,
        "links": [
            {
                "href": f"{base_url}/collections",
                "rel": "self",
                "type": "application/json"
            }
        ]
    }


def fetch_collection_by_id(cursor, collection_id):
    cursor.execute("""
        SELECT c.id, c.title, c.description, c.update_frequency, c.item_type,
        asText(extent(tg.trajectory)) AS extent,
        asText(extent(tg.trajectory)::tstzspan) AS extent_period,
        ( SELECT mf.crs FROM moving_features mf WHERE mf.collection_id =  %s LIMIT 1
            ) AS crs,

        (SELECT mf.trs FROM moving_features mf WHERE mf.collection_id =  %s LIMIT 1
            ) AS trs
        FROM collections c
        LEFT JOIN temporal_geometries tg ON tg.collection_id = c.id
        WHERE c.id = %s
        GROUP BY c.id, c.title
        ORDER BY c.created_at DESC;
    """, (collection_id,collection_id,collection_id))
    
    row = cursor.fetchone()
    if not row:
        return None
    
    columns = [desc[0] for desc in cursor.description]
    return dict(zip(columns, row))


def fetch_all_collections(cursor):
    cursor.execute("""
        SELECT c.id, c.title, c.description, c.update_frequency, c.item_type,
            asText(extent(tg.trajectory)) AS extent,
            asText(extent(tg.trajectory)::tstzspan) AS extent_period,
            ( SELECT mf.crs FROM moving_features mf WHERE mf.collection_id = c.id LIMIT 1
            ) AS crs,

            (SELECT mf.trs FROM moving_features mf WHERE mf.collection_id = c.id LIMIT 1
            ) AS trs

        FROM collections c
        LEFT JOIN temporal_geometries tg ON tg.collection_id = c.id
        GROUP BY c.id, c.title
        ORDER BY c.created_at DESC;
    """)
    

    rows = cursor.fetchall()
    columns = [desc[0] for desc in cursor.description]
    #CONSTRUCT THE collections dict
    collections = []
    for row in rows:
        collections.append(dict(zip(columns, row)))
    
    return collections




####################################################"Create and Replace helpers"
def validate_collection_data(data, is_update=False):
    errors = []
    validated = {}
    #if create aka post: operation
    if not is_update:
        # Post: Title mandatory:
        if "title" not in data:
            errors.append("Missing required field: title")
        else:
            validated["title"] = data["title"]
            # Honour a client-supplied id; otherwise derive one from the title.
            provided = data.get("id")
            if isinstance(provided, str) and provided.strip():
                validated["id"] = provided.strip().lower().replace(" ", "_")
            else:
                validated["id"] = data["title"].lower().replace(" ", "_")
    else: # Replace aka Put operation:
        if "title" in data:
            validated["title"] = data["title"]
    
    # Optional fields for POST AND PUT COLLECTION
    if "description" in data:
        validated["description"] = data["description"]
    
    if "itemType" in data:#PUT
        if data["itemType"] != "movingfeature":
            errors.append("itemType must be 'movingfeature'")
        validated["itemType"] = data["itemType"]
    elif not is_update:#POST
        validated["itemType"] = "movingfeature"
    
    if "updateFrequency" in data and not is_update:
        # updateFrequency can be set only for POST,  can't be replaced:
        validated["updateFrequency"] = data["updateFrequency"]
    

    return errors, validated

# Check collection existance by ID:
def collection_exists(cursor, collection_id):
    cursor.execute(
        "SELECT id FROM collections WHERE id = %s",
        (collection_id,)
    )
    return cursor.fetchone() is not None


#________________________________rr
def insert_collection(cursor, collection_id, data):
    cursor.execute("""
        INSERT INTO collections 
        (id, title, description, update_frequency, item_type)
        VALUES (%s, %s, %s, %s, %s)
        RETURNING id
    """, (
        collection_id,
        data.get("title"),
        data.get("description"),
        data.get("updateFrequency"),
        data.get("itemType", "movingfeature")
    ))
    return cursor.fetchone()[0]

def update_collection(cursor, collection_id, data):
    updates = []
    values = []
    
    if "title" in data:
        updates.append("title = %s")
        values.append(data["title"])
    if "description" in data:
        updates.append("description = %s")
        values.append(data["description"])
    if "itemType" in data:
        updates.append("item_type = %s")
        values.append(data["itemType"])
    updates.append("updated_at = NOW()")
    
    if updates:
        values.append(collection_id)
        cursor.execute(f"""
            UPDATE collections 
            SET {', '.join(updates)} 
            WHERE id = %s
        """, values)
        return True
    return False