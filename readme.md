Overview

Route-Agent is a coordination agent designed to operate alongside the G-Nav hybrid pathfinding system and a Hyperledger Besu blockchain network.

Its role is not to compute routes itself, but to act as a meta-planner that:

1. Monitors routes published by multiple vehicles on-chain

2. Requests alternative route candidates from each vehicle’s local pathfinding server

3. Evaluates inter-vehicle conflicts between routes

4. Produces per-vehicle recommendations that minimize conflicts while preserving route quality

5. The agent operates asynchronously and event-driven, without requiring global synchronization between vehicles.


Core Responsibilities

The Route-Agent is responsible for:

1. Discovering active vehicles
Vehicles are identified by their blockchain addresses, provided via configuration.

2. Reading routes from the blockchain
The agent periodically polls Besu to retrieve the most recent route for each vehicle.

3. Detecting route changes
Route fingerprints are used to detect when a vehicle publishes a new route.

4. Requesting alternative route candidates When a route change is detected, the agent queries the corresponding G-Nav server for: Dijkstra, A*, Combined Multiple Random route variants

5. Evaluating inter-vehicle conflicts
Each candidate route is compared against the current routes of other vehicles using geometric overlap analysis.

6. Ranking candidates and selecting a recommendation
Candidates are ranked using a cost function prioritizing conflict avoidance.

7. Publishing recommendations via API
Recommendations are exposed through REST endpoints for clients or visualization tools.

How to run?

.venv\Scripts\activate 

pip install -r requirements.txt

uvicorn main:app --host 0.0.0.0 --port 9000
