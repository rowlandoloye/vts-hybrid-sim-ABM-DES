# model.py — Mesa 2.x compatible elevator ABM + SimPy
from mesa import Agent, Model
from mesa.time import RandomActivation
from mesa.datacollection import DataCollector
import simpy
import numpy as np
import random


class RiderAgent(Agent):
    def __init__(self, unique_id, model, origin, dest):
        super().__init__(unique_id, model)
        self.origin = origin
        self.dest = dest

        self.wait_start = None
        self.wait_time = 0.0
        self.travel_time = 0.0
        self.journey_time = 0.0
        self.enter_time = None
        self.exit_time = None

        self.satisfaction = 0.0
        self.perceived_quality = 0.0
        self.comfort = 0.0

    def step(self):
        """
        First step: rider appears in lobby and starts waiting.
        After that, step() is a no-op.
        """
        if self.wait_start is None:
            self.wait_start = self.model.env.now
            self.model.lobby_waiting[self.origin].append(self)


class ElevatorAgent(Agent):
    def __init__(self, unique_id, model, capacity, speed, vibration, noise):
        super().__init__(unique_id, model)
        self.capacity = capacity
        self.speed = speed              # m/s
        self.floor_height = 3.5         # meters
        self.current_floor = 0
        self.passengers = []
        self.door_time = model.door_time
        self.reliability = 0.97

        self.vibration_level = vibration
        self.noise_level = noise

        # SimPy queue of floor requests
        self.request_store = simpy.Store(self.model.env)

        # Start the elevator's main SimPy process
        self.model.env.process(self.run())

    def step(self):
        """
        Scheduler calls this every Mesa tick.
        Elevator behaviour itself is handled by the SimPy process in run().
        """
        pass

    def move_to(self, floor):
        """SimPy process: move elevator to given floor."""
        distance = abs(floor - self.current_floor) * self.floor_height
        t = distance / self.speed

        # Reliability-related occasional extra delay
        if random.random() > self.reliability:
            t += random.uniform(10, 30)

        yield self.model.env.timeout(t)
        self.current_floor = floor

    def _unload(self, floor):
        """Unload passengers whose destination is this floor and compute metrics."""
        exiting = [p for p in self.passengers if p.dest == floor]

        for p in exiting:
            now = self.model.env.now
            p.exit_time = now
            p.travel_time = now - p.enter_time
            p.wait_time = p.enter_time - p.wait_start
            p.journey_time = now - p.wait_start

            # Simple satisfaction model: penalise long waits
            base_sat = 5.0 - (p.wait_time / 60.0)
            p.satisfaction = max(1.0, min(5.0, base_sat))
            p.perceived_quality = p.comfort

            self.passengers.remove(p)
            self.model.exited_riders.append(p)

    def _update_comfort(self):
        """Update comfort based on crowding, vibration, and noise."""
        if not self.passengers:
            return

        crowd = len(self.passengers) / self.capacity
        comfort = 5 - (crowd * 3) - (self.vibration_level * 1.5) - (self.noise_level / 20.0)

        for p in self.passengers:
            p.comfort = max(1.0, min(5.0, comfort + random.gauss(0, 0.5)))

    def run(self):
        """Main SimPy loop: wait for floor requests and serve them in sequence."""
        while True:
            floor = yield self.request_store.get()

            # Move to the requested floor
            yield from self.move_to(floor)
            yield self.model.env.timeout(self.door_time)

            # Unload
            self._unload(floor)

            # Load new riders
            waiting = list(self.model.lobby_waiting[floor])
            space = self.capacity - len(self.passengers)
            to_load = waiting[:space]

            for r in to_load:
                r.enter_time = self.model.env.now
                self.passengers.append(r)
                self.model.lobby_waiting[floor].remove(r)

            self._update_comfort()

            # Now serve destinations of current passengers (simple up/down sweep)
            dests = sorted({p.dest for p in self.passengers})
            for d in dests:
                if d == floor:
                    continue
                yield from self.move_to(d)
                yield self.model.env.timeout(self.door_time)
                self._unload(d)
                self._update_comfort()

    def request(self, floor):
        """External call: request the elevator to visit a floor."""
        self.request_store.put(floor)


class BuildingModel(Model):
    def __init__(
        self,
        N_floors=6,
        N_elevators=2,
        peak_hour=False,
        backup_power=True,
        door_time=10.6,
        capacity=16,
        vibration=1.01,
        noise=55.9,
        speed=3.0,
    ):
        super().__init__()

        # Mesa scheduler
        self.schedule = RandomActivation(self)

        self.N_floors = N_floors
        self.num_elevators = N_elevators
        self.peak_hour = peak_hour
        self.backup_power = backup_power

        self.door_time = door_time
        self.speed = speed

        # SimPy environment
        self.env = simpy.Environment()
        self.current_time = 0.0

        # State collections
        self.lobby_waiting = {f: [] for f in range(N_floors)}
        self.exited_riders = []

        # Create elevators (give each a unique_id via self.next_id())
        for _ in range(N_elevators):
            e = ElevatorAgent(self.next_id(), self, capacity, speed, vibration, noise)
            self.schedule.add(e)

        # Data collector
        self.datacollector = DataCollector(
            model_reporters={
                "Avg_Wait_Time": lambda m: np.mean([r.wait_time for r in m.exited_riders])
                if m.exited_riders else 0,
                "Avg_Journey_Time": lambda m: np.mean(
                    [r.journey_time for r in m.exited_riders]
                ) if m.exited_riders else 0,
                "Avg_Satisfaction": lambda m: np.mean(
                    [r.satisfaction for r in m.exited_riders]
                ) if m.exited_riders else 0,
                "Crowding": lambda m: np.mean(
                    [
                        len(e.passengers) / e.capacity
                        for e in m.schedule.agents
                        if isinstance(e, ElevatorAgent)
                    ]
                )
                if any(isinstance(e, ElevatorAgent) for e in m.schedule.agents)
                else 0,
            }
        )

        # Start rider generation process in SimPy
        self.env.process(self.generate_riders())

    def generate_riders(self):
        """Continuous rider arrival process (SimPy)."""
        while True:
            rate = 12 if self.peak_hour else 45
            inter_arrival = np.random.exponential(rate)
            yield self.env.timeout(inter_arrival)

            origin = random.choice(range(self.N_floors))
            dest = random.choice([f for f in range(self.N_floors) if f != origin])

            # Create rider and register with the Mesa scheduler
            r = RiderAgent(self.next_id(), self, origin, dest)
            self.schedule.add(r)

            # Immediately put them in the lobby (start waiting)
            r.step()

            # Call a random elevator
            elevators = [a for a in self.schedule.agents if isinstance(a, ElevatorAgent)]
            if elevators:
                random.choice(elevators).request(origin)

    def step(self):
        """
        One simulation step:
        - Advance SimPy to the next event
        - Step all Mesa agents (mostly a no-op except first rider step)
        - Collect metrics
        """
        # Advance the SimPy environment one event
        self.env.step()
        self.current_time = self.env.now

        # Step Mesa agents
        self.schedule.step()

        # Collect KPIs
        self.datacollector.collect(self)
