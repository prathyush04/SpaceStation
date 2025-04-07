// src/App.js
import React, { useState, useEffect } from 'react';
import { Container, Typography, Button, TextField, Paper, Grid, Box, Table, TableBody, TableCell, TableContainer, TableHead, TableRow, Select, MenuItem, FormControl, InputLabel } from '@mui/material';
import axios from 'axios';

function App() {
  const [containers, setContainers] = useState([]);
  const [items, setItems] = useState([]);
  const [wasteItems, setWasteItems] = useState([]);
  const [logs, setLogs] = useState([]);
  const [currentDate, setCurrentDate] = useState(new Date().toISOString().split('T')[0]);
  const [searchTerm, setSearchTerm] = useState('');
  const [searchResults, setSearchResults] = useState(null);
  const [selectedFile, setSelectedFile] = useState(null);
  const [simulationDays, setSimulationDays] = useState(1);
  const [placementData, setPlacementData] = useState(null);

  // Fetch initial data
  useEffect(() => {
    fetchContainers();
    fetchItems();
    fetchWasteItems();
    fetchLogs();
  }, []);

  const fetchContainers = async () => {
    try {
      const response = await axios.get('http://localhost:8000/api/export/arrangement');
      // Parse containers from CSV (simplified)
      const containerData = response.data.csv.split('\n').slice(1).map(line => {
        const parts = line.split(',');
        return {
          containerId: parts[1],
          zone: parts[1].startsWith('contA') ? 'Crew Quarters' : 
               parts[1].startsWith('contB') ? 'Airlock' : 'Laboratory'
        };
      }).filter(c => c.containerId);
      
      setContainers(containerData);
    } catch (error) {
      console.error('Error fetching containers:', error);
    }
  };

  const fetchItems = async () => {
    try {
      const response = await axios.get('http://localhost:8000/api/search?itemName=');
      if (response.data.found) {
        setItems([response.data.item]);
      }
    } catch (error) {
      console.error('Error fetching items:', error);
    }
  };

  const fetchWasteItems = async () => {
    try {
      const response = await axios.get('http://localhost:8000/api/waste/identify');
      setWasteItems(response.data.wasteItems);
    } catch (error) {
      console.error('Error fetching waste items:', error);
    }
  };

  const fetchLogs = async () => {
    try {
      const response = await axios.get('http://localhost:8000/api/logs');
      setLogs(response.data.logs);
    } catch (error) {
      console.error('Error fetching logs:', error);
    }
  };

  const handleSearch = async () => {
    try {
      const response = await axios.get(`http://localhost:8000/api/search?itemName=${searchTerm}`);
      setSearchResults(response.data);
    } catch (error) {
      console.error('Error searching:', error);
    }
  };

  const handleRetrieve = async (itemId) => {
    try {
      await axios.post('http://localhost:8000/api/retrieve', {
        itemId,
        userId: 'astronaut1',
        timestamp: new Date().toISOString()
      });
      alert('Item retrieved successfully');
      fetchItems();
      fetchLogs();
    } catch (error) {
      console.error('Error retrieving item:', error);
    }
  };

  const handlePlace = async (itemId, containerId, position) => {
    try {
      await axios.post('http://localhost:8000/api/place', {
        itemId,
        userId: 'astronaut1',
        timestamp: new Date().toISOString(),
        containerId,
        position
      });
      alert('Item placed successfully');
      fetchItems();
      fetchLogs();
    } catch (error) {
      console.error('Error placing item:', error);
    }
  };

  const handleFileUpload = async (type) => {
    if (!selectedFile) return;
    
    const formData = new FormData();
    formData.append('file', selectedFile);
    
    try {
      const endpoint = type === 'items' ? '/api/import/items' : '/api/import/containers';
      const response = await axios.post(`http://localhost:8000${endpoint}`, formData, {
        headers: {
          'Content-Type': 'multipart/form-data'
        }
      });
      
      alert(`Successfully imported ${response.data.itemsImported || response.data.containersImported} ${type}`);
      if (type === 'items') {
        fetchItems();
      } else {
        fetchContainers();
      }
    } catch (error) {
      console.error('Error uploading file:', error);
    }
  };

  const handleSimulateDay = async () => {
    try {
      const response = await axios.post('http://localhost:8000/api/simulate/day', {
        numOfDays: simulationDays,
        itemsToBeUsedPerDay: items.map(item => ({ itemId: item.itemId }))
      });
      
      setCurrentDate(response.data.newDate.split('T')[0]);
      fetchItems();
      fetchWasteItems();
      fetchLogs();
      
      alert(`Simulated ${simulationDays} day(s). ${response.data.changes.itemsExpired.length} items expired.`);
    } catch (error) {
      console.error('Error simulating day:', error);
    }
  };

  const handleGenerateReturnPlan = async () => {
    try {
      const response = await axios.post('http://localhost:8000/api/waste/return-plan', {
        undockingContainerId: 'returnCont1',
        undockingDate: new Date().toISOString(),
        maxWeight: 1000
      });
      
      alert(`Return plan generated for ${response.data.returnManifest.returnItems.length} items`);
    } catch (error) {
      console.error('Error generating return plan:', error);
    }
  };

  const handleCompleteUndocking = async () => {
    try {
      const response = await axios.post('http://localhost:8000/api/waste/complete-undocking', {
        undockingContainerId: 'returnCont1',
        timestamp: new Date().toISOString()
      });
      
      alert(`Undocking completed. ${response.data.itemsRemoved} items removed.`);
      fetchItems();
      fetchWasteItems();
      fetchLogs();
    } catch (error) {
      console.error('Error completing undocking:', error);
    }
  };

  return (
    <Container maxWidth="lg">
      <Box sx={{ my: 4 }}>
        <Typography variant="h4" component="h1" gutterBottom>
          Space Station Cargo Management System
        </Typography>
        <Typography variant="subtitle1" gutterBottom>
          Current Date: {currentDate}
        </Typography>
        
        <Grid container spacing={3}>
          {/* Search Section */}
          <Grid item xs={12} md={6}>
            <Paper sx={{ p: 2 }}>
              <Typography variant="h6" gutterBottom>
                Item Search
              </Typography>
              <Box sx={{ display: 'flex', gap: 2, mb: 2 }}>
                <TextField
                  label="Search by name or ID"
                  value={searchTerm}
                  onChange={(e) => setSearchTerm(e.target.value)}
                  fullWidth
                />
                <Button variant="contained" onClick={handleSearch}>
                  Search
                </Button>
              </Box>
              
              {searchResults && (
                <Box>
                  {searchResults.found ? (
                    <Box>
                      <Typography>Found: {searchResults.item.name}</Typography>
                      <Typography>Container: {searchResults.item.containerId}</Typography>
                      <Typography>Position: {JSON.stringify(searchResults.item.position)}</Typography>
                      
                      {searchResults.retrievalSteps.length > 0 && (
                        <Box mt={2}>
                          <Typography variant="subtitle2">Retrieval Steps:</Typography>
                          <ol>
                            {searchResults.retrievalSteps.map(step => (
                              <li key={step.step}>{step.action} {step.itemName}</li>
                            ))}
                          </ol>
                        </Box>
                      )}
                      
                      <Button 
                        variant="contained" 
                        color="primary" 
                        onClick={() => handleRetrieve(searchResults.item.itemId)}
                        sx={{ mt: 2 }}
                      >
                        Retrieve Item
                      </Button>
                    </Box>
                  ) : (
                    <Typography>Item not found</Typography>
                  )}
                </Box>
              )}
            </Paper>
          </Grid>
          
          {/* Waste Management */}
          <Grid item xs={12} md={6}>
            <Paper sx={{ p: 2 }}>
              <Typography variant="h6" gutterBottom>
                Waste Management
              </Typography>
              
              <TableContainer>
                <Table size="small">
                  <TableHead>
                    <TableRow>
                      <TableCell>Item</TableCell>
                      <TableCell>Reason</TableCell>
                      <TableCell>Container</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {wasteItems.map(item => (
                      <TableRow key={item.itemId}>
                        <TableCell>{item.name}</TableCell>
                        <TableCell>{item.reason}</TableCell>
                        <TableCell>{item.containerId}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TableContainer>
              
              <Box sx={{ display: 'flex', gap: 2, mt: 2 }}>
                <Button variant="contained" onClick={handleGenerateReturnPlan}>
                  Generate Return Plan
                </Button>
                <Button variant="contained" onClick={handleCompleteUndocking}>
                  Complete Undocking
                </Button>
              </Box>
            </Paper>
          </Grid>
          
          {/* Time Simulation */}
          <Grid item xs={12}>
            <Paper sx={{ p: 2 }}>
              <Typography variant="h6" gutterBottom>
                Time Simulation
              </Typography>
              
              <Box sx={{ display: 'flex', gap: 2, alignItems: 'center' }}>
                <TextField
                  label="Days to simulate"
                  type="number"
                  value={simulationDays}
                  onChange={(e) => setSimulationDays(parseInt(e.target.value))}
                  sx={{ width: 120 }}
                />
                <Button variant="contained" onClick={handleSimulateDay}>
                  Simulate Days
                </Button>
              </Box>
            </Paper>
          </Grid>
          
          {/* Data Import */}
          <Grid item xs={12} md={6}>
            <Paper sx={{ p: 2 }}>
              <Typography variant="h6" gutterBottom>
                Data Import
              </Typography>
              
              <Box sx={{ display: 'flex', gap: 2, mb: 2 }}>
                <input
                  type="file"
                  onChange={(e) => setSelectedFile(e.target.files[0])}
                />
              </Box>
              
              <Box sx={{ display: 'flex', gap: 2 }}>
                <Button 
                  variant="contained" 
                  onClick={() => handleFileUpload('items')}
                  disabled={!selectedFile}
                >
                  Import Items
                </Button>
                <Button 
                  variant="contained" 
                  onClick={() => handleFileUpload('containers')}
                  disabled={!selectedFile}
                >
                  Import Containers
                </Button>
              </Box>
            </Paper>
          </Grid>
          
          {/* Placement Recommendations */}
          <Grid item xs={12} md={6}>
            <Paper sx={{ p: 2 }}>
              <Typography variant="h6" gutterBottom>
                Placement Recommendations
              </Typography>
              
              <Button 
                variant="contained" 
                onClick={async () => {
                  try {
                    const response = await axios.post('http://localhost:8000/api/placement', {
                      items: items.map(item => ({
                        itemId: item.itemId,
                        name: item.name,
                        width: item.position.endCoordinates.width - item.position.startCoordinates.width,
                        depth: item.position.endCoordinates.depth - item.position.startCoordinates.depth,
                        height: item.position.endCoordinates.height - item.position.startCoordinates.height,
                        mass: 1, // Default mass
                        priority: 50, // Default priority
                        expiryDate: null,
                        usageLimit: null,
                        preferredZone: 'Crew Quarters'
                      })),
                      containers: containers.map(container => ({
                        containerId: container.containerId,
                        zone: container.zone,
                        width: 100, // Default container size
                        depth: 85,
                        height: 200
                      }))
                    });
                    setPlacementData(response.data);
                  } catch (error) {
                    console.error('Error getting placement:', error);
                  }
                }}
              >
                Generate Placement
              </Button>
              
              {placementData && (
                <Box mt={2}>
                  <Typography variant="subtitle2">Placements:</Typography>
                  <pre>{JSON.stringify(placementData.placements, null, 2)}</pre>
                </Box>
              )}
            </Paper>
          </Grid>
          
          {/* Activity Logs */}
          <Grid item xs={12}>
            <Paper sx={{ p: 2 }}>
              <Typography variant="h6" gutterBottom>
                Activity Logs
              </Typography>
              
              <TableContainer>
                <Table size="small">
                  <TableHead>
                    <TableRow>
                      <TableCell>Timestamp</TableCell>
                      <TableCell>User</TableCell>
                      <TableCell>Action</TableCell>
                      <TableCell>Item</TableCell>
                      <TableCell>Details</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {logs.slice(0, 10).map(log => (
                      <TableRow key={log.timestamp}>
                        <TableCell>{new Date(log.timestamp).toLocaleString()}</TableCell>
                        <TableCell>{log.userId || 'System'}</TableCell>
                        <TableCell>{log.actionType}</TableCell>
                        <TableCell>{log.itemId || 'N/A'}</TableCell>
                        <TableCell>{log.details}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TableContainer>
            </Paper>
          </Grid>
        </Grid>
      </Box>
    </Container>
  );
}

export default App;