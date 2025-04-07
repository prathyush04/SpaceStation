# main.py (FastAPI backend)
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional, Dict
from datetime import datetime, timedelta
import csv
import io
import sqlite3
import uuid
from enum import Enum
import math

app = FastAPI()

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Database setup
conn = sqlite3.connect('cargo.db', check_same_thread=False)
cursor = conn.cursor()

# Create tables
cursor.execute('''
CREATE TABLE IF NOT EXISTS containers (
    container_id TEXT PRIMARY KEY,
    zone TEXT NOT NULL,
    width REAL NOT NULL,
    depth REAL NOT NULL,
    height REAL NOT NULL
)
''')

cursor.execute('''
CREATE TABLE IF NOT EXISTS items (
    item_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    width REAL NOT NULL,
    depth REAL NOT NULL,
    height REAL NOT NULL,
    mass REAL NOT NULL,
    priority INTEGER NOT NULL,
    expiry_date TEXT,
    usage_limit INTEGER,
    remaining_uses INTEGER,
    preferred_zone TEXT,
    container_id TEXT,
    position_start_width REAL,
    position_start_depth REAL,
    position_start_height REAL,
    position_end_width REAL,
    position_end_depth REAL,
    position_end_height REAL,
    is_waste BOOLEAN DEFAULT 0,
    FOREIGN KEY (container_id) REFERENCES containers (container_id)
)
''')

cursor.execute('''
CREATE TABLE IF NOT EXISTS logs (
    log_id TEXT PRIMARY KEY,
    timestamp TEXT NOT NULL,
    user_id TEXT,
    action_type TEXT NOT NULL,
    item_id TEXT,
    details TEXT,
    FOREIGN KEY (item_id) REFERENCES items (item_id)
)
''')

conn.commit()

# Models
class Item(BaseModel):
    itemId: str
    name: str
    width: float
    depth: float
    height: float
    mass: float
    priority: int
    expiryDate: Optional[str] = None
    usageLimit: Optional[int] = None
    preferredZone: str

class Container(BaseModel):
    containerId: str
    zone: str
    width: float
    depth: float
    height: float

class Position(BaseModel):
    startCoordinates: Dict[str, float]
    endCoordinates: Dict[str, float]

class PlacementRequest(BaseModel):
    items: List[Item]
    containers: List[Container]

class PlacementResponse(BaseModel):
    success: bool
    placements: List[Dict]
    rearrangements: List[Dict]

class SearchResponse(BaseModel):
    success: bool
    found: bool
    item: Optional[Dict]
    retrievalSteps: List[Dict]

class RetrieveRequest(BaseModel):
    itemId: str
    userId: str
    timestamp: str

class PlaceRequest(BaseModel):
    itemId: str
    userId: str
    timestamp: str
    containerId: str
    position: Position

class WasteIdentifyResponse(BaseModel):
    success: bool
    wasteItems: List[Dict]

class ReturnPlanRequest(BaseModel):
    undockingContainerId: str
    undockingDate: str
    maxWeight: float

class ReturnPlanResponse(BaseModel):
    success: bool
    returnPlan: List[Dict]
    retrievalSteps: List[Dict]
    returnManifest: Dict

class UndockingRequest(BaseModel):
    undockingContainerId: str
    timestamp: str

class UndockingResponse(BaseModel):
    success: bool
    itemsRemoved: int

class SimulateRequest(BaseModel):
    numOfDays: Optional[int] = None
    toTimestamp: Optional[str] = None
    itemsToBeUsedPerDay: List[Dict]

class SimulateResponse(BaseModel):
    success: bool
    newDate: str
    changes: Dict

class LogsResponse(BaseModel):
    logs: List[Dict]

# Helper functions
def log_action(user_id: str, action_type: str, item_id: str = None, details: str = None):
    log_id = str(uuid.uuid4())
    timestamp = datetime.utcnow().isoformat()
    cursor.execute('''
    INSERT INTO logs (log_id, timestamp, user_id, action_type, item_id, details)
    VALUES (?, ?, ?, ?, ?, ?)
    ''', (log_id, timestamp, user_id, action_type, item_id, details))
    conn.commit()

def get_item_by_id(item_id: str):
    cursor.execute('SELECT * FROM items WHERE item_id = ?', (item_id,))
    return cursor.fetchone()

def get_container_by_id(container_id: str):
    cursor.execute('SELECT * FROM containers WHERE container_id = ?', (container_id,))
    return cursor.fetchone()

def get_items_in_container(container_id: str):
    cursor.execute('''
    SELECT * FROM items 
    WHERE container_id = ? AND is_waste = 0
    ORDER BY position_start_depth ASC, position_start_height ASC, position_start_width ASC
    ''', (container_id,))
    return cursor.fetchall()

def calculate_retrieval_steps(container_id: str, target_item_id: str):
    items = get_items_in_container(container_id)
    target_item = None
    blocking_items = []
    
    for item in items:
        if item[0] == target_item_id:
            target_item = item
            break
    
    if not target_item:
        return []
    
    target_depth = target_item[11]  # position_start_depth
    steps = []
    
    for item in items:
        if item[11] < target_depth:  # Items in front of target
            steps.append({
                'step': len(steps) + 1,
                'action': 'remove',
                'itemId': item[0],
                'itemName': item[1]
            })
    
    return steps

def check_item_expiry():
    current_date = datetime.utcnow().date().isoformat()
    cursor.execute('''
    UPDATE items 
    SET is_waste = 1 
    WHERE expiry_date IS NOT NULL AND expiry_date <= ? AND is_waste = 0
    ''', (current_date,))
    conn.commit()

def mark_depleted_items():
    cursor.execute('''
    UPDATE items 
    SET is_waste = 1 
    WHERE usage_limit IS NOT NULL AND remaining_uses <= 0 AND is_waste = 0
    ''', ())
    conn.commit()

# 3D Bin Packing Algorithm
class MaximalRectangleBinPack:
    def __init__(self, width, height, depth):
        self.width = width
        self.height = height
        self.depth = depth
        self.used_rectangles = []
        self.free_rectangles = [{'x': 0, 'y': 0, 'z': 0, 'width': width, 'height': height, 'depth': depth}]
    
    def insert(self, item_width, item_height, item_depth, priority):
        best_score = float('inf')
        best_rect = None
        best_free_index = -1
        
        for i, free_rect in enumerate(self.free_rectangles):
            if free_rect['width'] >= item_width and free_rect['height'] >= item_height and free_rect['depth'] >= item_depth:
                score = self.score_by_priority(free_rect, priority)
                if score < best_score:
                    best_score = score
                    best_rect = free_rect.copy()
                    best_free_index = i
        
        if best_rect is None:
            return None
        
        # Place the item
        new_rect = {
            'x': best_rect['x'],
            'y': best_rect['y'],
            'z': best_rect['z'],
            'width': item_width,
            'height': item_height,
            'depth': item_depth
        }
        self.used_rectangles.append(new_rect)
        
        # Split the remaining space
        remaining_width = best_rect['width'] - item_width
        remaining_height = best_rect['height'] - item_height
        remaining_depth = best_rect['depth'] - item_depth
        
        if remaining_width > 0 and remaining_height > 0 and remaining_depth > 0:
            # Split into 3 new rectangles
            self.free_rectangles.append({
                'x': best_rect['x'] + item_width,
                'y': best_rect['y'],
                'z': best_rect['z'],
                'width': remaining_width,
                'height': item_height,
                'depth': item_depth
            })
            self.free_rectangles.append({
                'x': best_rect['x'],
                'y': best_rect['y'] + item_height,
                'z': best_rect['z'],
                'width': best_rect['width'],
                'height': remaining_height,
                'depth': item_depth
            })
            self.free_rectangles.append({
                'x': best_rect['x'],
                'y': best_rect['y'],
                'z': best_rect['z'] + item_depth,
                'width': best_rect['width'],
                'height': best_rect['height'],
                'depth': remaining_depth
            })
        
        del self.free_rectangles[best_free_index]
        
        return new_rect
    
    def score_by_priority(self, rect, priority):
        # Higher priority items should be closer to the front (lower z)
        # and more accessible (lower x and y)
        return rect['z'] * 0.5 + rect['x'] * 0.3 + rect['y'] * 0.2 - priority * 0.1

# API Endpoints
@app.post("/api/placement", response_model=PlacementResponse)
async def placement_recommendations(request: PlacementRequest):
    try:
        # Save containers to DB
        for container in request.containers:
            cursor.execute('''
            INSERT OR REPLACE INTO containers (container_id, zone, width, depth, height)
            VALUES (?, ?, ?, ?, ?)
            ''', (container.containerId, container.zone, container.width, container.depth, container.height))
        
        # Initialize bin packers for each container
        containers = {}
        for container in request.containers:
            containers[container.containerId] = {
                'bin_packer': MaximalRectangleBinPack(container.width, container.height, container.depth),
                'zone': container.zone
            }
        
        # Sort items by priority (descending) and size (ascending)
        sorted_items = sorted(request.items, key=lambda x: (-x.priority, x.width * x.height * x.depth))
        
        placements = []
        rearrangements = []
        
        for item in sorted_items:
            placed = False
            preferred_containers = [c for c in request.containers if c.zone == item.preferredZone]
            other_containers = [c for c in request.containers if c.zone != item.preferredZone]
            
            # Try preferred containers first
            for container in preferred_containers + other_containers:
                bin_packer = containers[container.containerId]['bin_packer']
                
                # Try all possible rotations
                rotations = [
                    (item.width, item.height, item.depth),
                    (item.width, item.depth, item.height),
                    (item.height, item.width, item.depth),
                    (item.height, item.depth, item.width),
                    (item.depth, item.width, item.height),
                    (item.depth, item.height, item.width)
                ]
                
                for rot in rotations:
                    rect = bin_packer.insert(rot[0], rot[1], rot[2], item.priority)
                    if rect:
                        placements.append({
                            'itemId': item.itemId,
                            'containerId': container.containerId,
                            'position': {
                                'startCoordinates': {
                                    'width': rect['x'],
                                    'depth': rect['z'],
                                    'height': rect['y']
                                },
                                'endCoordinates': {
                                    'width': rect['x'] + rect['width'],
                                    'depth': rect['z'] + rect['depth'],
                                    'height': rect['y'] + rect['height']
                                }
                            }
                        })
                        
                        # Save to DB
                        cursor.execute('''
                        INSERT INTO items (
                            item_id, name, width, depth, height, mass, priority, 
                            expiry_date, usage_limit, remaining_uses, preferred_zone,
                            container_id, position_start_width, position_start_depth, 
                            position_start_height, position_end_width, position_end_depth, 
                            position_end_height, is_waste
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ''', (
                            item.itemId, item.name, item.width, item.depth, item.height, item.mass, item.priority,
                            item.expiryDate, item.usageLimit, item.usageLimit, item.preferredZone,
                            container.containerId, rect['x'], rect['z'], rect['y'],
                            rect['x'] + rect['width'], rect['z'] + rect['depth'], rect['y'] + rect['height'], 0
                        ))
                        
                        placed = True
                        break
                    if placed:
                        break
                if placed:
                    break
            
            if not placed:
                # Need to rearrange - find lower priority items to move
                # (Implementation simplified for this example)
                pass
        
        conn.commit()
        return PlacementResponse(success=True, placements=placements, rearrangements=rearrangements)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/search", response_model=SearchResponse)
async def search_item(itemId: Optional[str] = None, itemName: Optional[str] = None, userId: Optional[str] = None):
    try:
        if not itemId and not itemName:
            raise HTTPException(status_code=400, detail="Either itemId or itemName must be provided")
        
        query = 'SELECT * FROM items WHERE '
        params = []
        
        if itemId:
            query += 'item_id = ?'
            params.append(itemId)
        else:
            query += 'name LIKE ?'
            params.append(f'%{itemName}%')
        
        cursor.execute(query, params)
        item = cursor.fetchone()
        
        if not item:
            return SearchResponse(success=True, found=False)
        
        retrieval_steps = calculate_retrieval_steps(item[12], item[0]) if item[12] else []
        
        return SearchResponse(
            success=True,
            found=True,
            item={
                'itemId': item[0],
                'name': item[1],
                'containerId': item[12],
                'zone': get_container_by_id(item[12])[1] if item[12] else None,
                'position': {
                    'startCoordinates': {
                        'width': item[13],
                        'depth': item[14],
                        'height': item[15]
                    },
                    'endCoordinates': {
                        'width': item[16],
                        'depth': item[17],
                        'height': item[18]
                    }
                }
            },
            retrievalSteps=retrieval_steps
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/retrieve", response_model=Dict)
async def retrieve_item(request: RetrieveRequest):
    try:
        cursor.execute('SELECT * FROM items WHERE item_id = ?', (request.itemId,))
        item = cursor.fetchone()
        
        if not item:
            raise HTTPException(status_code=404, detail="Item not found")
        
        # Decrement remaining uses if applicable
        if item[9] is not None:  # remaining_uses
            new_uses = item[9] - 1
            cursor.execute('UPDATE items SET remaining_uses = ? WHERE item_id = ?', (new_uses, request.itemId))
        
        # Log the retrieval
        log_action(request.userId, "retrieval", request.itemId, f"Retrieved from container {item[12]}")
        
        conn.commit()
        return {"success": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/place", response_model=Dict)
async def place_item(request: PlaceRequest):
    try:
        cursor.execute('''
        UPDATE items 
        SET container_id = ?,
            position_start_width = ?,
            position_start_depth = ?,
            position_start_height = ?,
            position_end_width = ?,
            position_end_depth = ?,
            position_end_height = ?
        WHERE item_id = ?
        ''', (
            request.containerId,
            request.position.startCoordinates['width'],
            request.position.startCoordinates['depth'],
            request.position.startCoordinates['height'],
            request.position.endCoordinates['width'],
            request.position.endCoordinates['depth'],
            request.position.endCoordinates['height'],
            request.itemId
        ))
        
        log_action(request.userId, "placement", request.itemId, 
                  f"Placed in container {request.containerId} at {request.position}")
        
        conn.commit()
        return {"success": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/waste/identify", response_model=WasteIdentifyResponse)
async def identify_waste():
    try:
        check_item_expiry()
        mark_depleted_items()
        
        cursor.execute('SELECT * FROM items WHERE is_waste = 1')
        waste_items = cursor.fetchall()
        
        return WasteIdentifyResponse(
            success=True,
            wasteItems=[{
                'itemId': item[0],
                'name': item[1],
                'reason': 'Expired' if item[7] and datetime.strptime(item[7], '%Y-%m-%d').date() <= datetime.utcnow().date() else 'Out of Uses',
                'containerId': item[12],
                'position': {
                    'startCoordinates': {
                        'width': item[13],
                        'depth': item[14],
                        'height': item[15]
                    },
                    'endCoordinates': {
                        'width': item[16],
                        'depth': item[17],
                        'height': item[18]
                    }
                }
            } for item in waste_items]
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/waste/return-plan", response_model=ReturnPlanResponse)
async def waste_return_plan(request: ReturnPlanRequest):
    try:
        cursor.execute('''
        SELECT * FROM items 
        WHERE is_waste = 1
        ORDER BY mass DESC
        ''')
        waste_items = cursor.fetchall()
        
        total_weight = 0
        return_items = []
        return_plan = []
        
        for item in waste_items:
            if total_weight + item[6] > request.maxWeight:
                continue
            
            return_items.append({
                'itemId': item[0],
                'name': item[1],
                'reason': 'Expired' if item[7] and datetime.strptime(item[7], '%Y-%m-%d').date() <= datetime.utcnow().date() else 'Out of Uses'
            })
            
            if item[12]:  # If in a container
                return_plan.append({
                    'step': len(return_plan) + 1,
                    'itemId': item[0],
                    'itemName': item[1],
                    'fromContainer': item[12],
                    'toContainer': request.undockingContainerId
                })
            
            total_weight += item[6]
        
        # Calculate retrieval steps (simplified)
        retrieval_steps = []
        for item in waste_items:
            if item[12]:
                steps = calculate_retrieval_steps(item[12], item[0])
                retrieval_steps.extend(steps)
        
        return ReturnPlanResponse(
            success=True,
            returnPlan=return_plan,
            retrievalSteps=retrieval_steps,
            returnManifest={
                'undockingContainerId': request.undockingContainerId,
                'undockingDate': request.undockingDate,
                'returnItems': return_items,
                'totalVolume': sum(i[2]*i[3]*i[4] for i in waste_items),
                'totalWeight': total_weight
            }
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/waste/complete-undocking", response_model=UndockingResponse)
async def complete_undocking(request: UndockingRequest):
    try:
        cursor.execute('DELETE FROM items WHERE is_waste = 1')
        count = cursor.rowcount
        conn.commit()
        
        log_action(None, "undocking", None, f"Completed undocking of container {request.undockingContainerId}")
        
        return UndockingResponse(success=True, itemsRemoved=count)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/simulate/day", response_model=SimulateResponse)
async def simulate_day(request: SimulateRequest):
    try:
        current_date = datetime.utcnow()
        
        if request.numOfDays:
            new_date = current_date + timedelta(days=request.numOfDays)
        elif request.toTimestamp:
            new_date = datetime.fromisoformat(request.toTimestamp)
        else:
            raise HTTPException(status_code=400, detail="Either numOfDays or toTimestamp must be provided")
        
        items_used = []
        items_expired = []
        items_depleted = []
        
        # Process items to be used
        for item_usage in request.itemsToBeUsedPerDay:
            item_id = item_usage.get('itemId')
            item_name = item_usage.get('name')
            
            if item_id:
                cursor.execute('SELECT * FROM items WHERE item_id = ?', (item_id,))
            else:
                cursor.execute('SELECT * FROM items WHERE name = ?', (item_name,))
            
            item = cursor.fetchone()
            
            if item:
                if item[9] is not None:  # remaining_uses
                    new_uses = item[9] - 1
                    cursor.execute('UPDATE items SET remaining_uses = ? WHERE item_id = ?', (new_uses, item[0]))
                    
                    if new_uses <= 0:
                        items_depleted.append({
                            'itemId': item[0],
                            'name': item[1]
                        })
                
                items_used.append({
                    'itemId': item[0],
                    'name': item[1],
                    'remainingUses': new_uses if item[9] is not None else None
                })
        
        # Check for expired items
        check_item_expiry()
        cursor.execute('''
        SELECT item_id, name FROM items 
        WHERE is_waste = 1 AND expiry_date <= ?
        ''', (new_date.date().isoformat(),))
        expired_items = cursor.fetchall()
        
        for item in expired_items:
            items_expired.append({
                'itemId': item[0],
                'name': item[1]
            })
        
        conn.commit()
        
        return SimulateResponse(
            success=True,
            newDate=new_date.isoformat(),
            changes={
                'itemsUsed': items_used,
                'itemsExpired': items_expired,
                'itemsDepletedToday': items_depleted
            }
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/import/items")
async def import_items(file: UploadFile = File(...)):
    try:
        contents = await file.read()
        text = io.StringIO(contents.decode('utf-8'))
        reader = csv.DictReader(text)
        
        imported = 0
        errors = []
        
        for i, row in enumerate(reader, 1):
            try:
                cursor.execute('''
                INSERT INTO items (
                    item_id, name, width, depth, height, mass, priority,
                    expiry_date, usage_limit, remaining_uses, preferred_zone,
                    is_waste
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    row['Item ID'],
                    row['Name'],
                    float(row['Width (cm)']),
                    float(row['Depth (cm)']),
                    float(row['Height (cm)']),
                    float(row['Mass (kg)']),
                    int(row['Priority (1-100)']),
                    row['Expiry Date (ISO Format)'] if row['Expiry Date (ISO Format)'] else None,
                    int(row['Usage Limit']) if row['Usage Limit'] else None,
                    int(row['Usage Limit']) if row['Usage Limit'] else None,
                    row['Preferred Zone'],
                    0
                ))
                imported += 1
            except Exception as e:
                errors.append({'row': i, 'message': str(e)})
        
        conn.commit()
        return {"success": True, "itemsImported": imported, "errors": errors}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/import/containers")
async def import_containers(file: UploadFile = File(...)):
    try:
        contents = await file.read()
        text = io.StringIO(contents.decode('utf-8'))
        reader = csv.DictReader(text)
        
        imported = 0
        errors = []
        
        for i, row in enumerate(reader, 1):
            try:
                cursor.execute('''
                INSERT OR REPLACE INTO containers (
                    container_id, zone, width, depth, height
                ) VALUES (?, ?, ?, ?, ?)
                ''', (
                    row['Container ID'],
                    row['Zone'],
                    float(row['Width(cm)']),
                    float(row['Depth(cm)']),
                    float(row['Height(height)'])
                ))
                imported += 1
            except Exception as e:
                errors.append({'row': i, 'message': str(e)})
        
        conn.commit()
        return {"success": True, "containersImported": imported, "errors": errors}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/export/arrangement")
async def export_arrangement():
    try:
        cursor.execute('''
        SELECT 
            i.item_id, 
            i.container_id, 
            i.position_start_width, i.position_start_depth, i.position_start_height,
            i.position_end_width, i.position_end_depth, i.position_end_height
        FROM items i
        WHERE i.container_id IS NOT NULL
        ''')
        
        rows = cursor.fetchall()
        csv_data = "Item ID,Container ID,Coordinates (W1,D1,H1),(W2,D2,H2)\n"
        
        for row in rows:
            csv_data += f"{row[0]},{row[1]},({row[2]},{row[3]},{row[4]}),({row[5]},{row[6]},{row[7]})\n"
        
        return {"success": True, "csv": csv_data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/logs", response_model=LogsResponse)
async def get_logs(
    startDate: Optional[str] = None,
    endDate: Optional[str] = None,
    itemId: Optional[str] = None,
    userId: Optional[str] = None,
    actionType: Optional[str] = None
):
    try:
        query = 'SELECT * FROM logs'
        conditions = []
        params = []
        
        if startDate:
            conditions.append('timestamp >= ?')
            params.append(startDate)
        if endDate:
            conditions.append('timestamp <= ?')
            params.append(endDate)
        if itemId:
            conditions.append('item_id = ?')
            params.append(itemId)
        if userId:
            conditions.append('user_id = ?')
            params.append(userId)
        if actionType:
            conditions.append('action_type = ?')
            params.append(actionType)
        
        if conditions:
            query += ' WHERE ' + ' AND '.join(conditions)
        
        query += ' ORDER BY timestamp DESC'
        
        cursor.execute(query, params)
        logs = cursor.fetchall()
        
        return LogsResponse(logs=[{
            'timestamp': log[1],
            'userId': log[2],
            'actionType': log[3],
            'itemId': log[4],
            'details': log[5]
        } for log in logs])
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)