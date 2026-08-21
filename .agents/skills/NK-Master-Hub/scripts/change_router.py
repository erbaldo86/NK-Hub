import asyncio
import os
import time
from typing import Dict, List, Set, Tuple

class GraphValidationError(Exception):
    """Eccezione sollevata in caso di fallimento della validazione del grafo."""
    pass

class CycleDetectedError(Exception):
    """Eccezione sollevata in caso di ciclo rilevato nel grafo dipendenze."""
    pass

# -------------------------------------------------------------
# ChangeRouterValidator using Kahn's Algorithm
# -------------------------------------------------------------
class ChangeRouterValidator:
    MAX_NODES = 200
    MAX_DEPTH = 50

    @classmethod
    def validate_and_sort(cls, dependencies: Dict[str, List[str]], frontend_status: str = "") -> List[str]:
        # 1. Valida dimensione del grafo
        if len(dependencies) > cls.MAX_NODES:
            raise GraphValidationError(f"Grafo troppo grande: {len(dependencies)} nodi. Max consentito: {cls.MAX_NODES}")
        
        # Sanitizzazione chiavi e valori
        sanitized = {}
        for k, v in dependencies.items():
            if not isinstance(k, str) or not all(c.isalnum() or c in "-_" for c in k):
                raise GraphValidationError(f"Nome nodo non valido: {k}")
            for neighbor in v:
                if not isinstance(neighbor, str) or not all(c.isalnum() or c in "-_" for c in neighbor):
                    raise GraphValidationError(f"Nome nodo dipendente non valido: {neighbor}")
            sanitized[k] = list(set(v))

        # Raccogli tutti i nodi menzionati nel grafo
        all_nodes = set(sanitized.keys())
        for neighbors in sanitized.values():
            all_nodes.update(neighbors)
        
        # Assicura che ogni nodo sia definito in sanitized
        for node in all_nodes:
            if node not in sanitized:
                sanitized[node] = []

        # Calcolo dei gradi di ingresso (in-degree)
        in_degree = {u: 0 for u in sanitized}
        for u in sanitized:
            for v in sanitized[u]:
                in_degree[v] += 1

        # Coda per nodi con grado di ingresso 0
        queue = [u for u in in_degree if in_degree[u] == 0]
        topo_order = []
        depth_map = {u: 1 for u in in_degree}

        # Algoritmo di Kahn iterativo
        while queue:
            u = queue.pop(0)
            topo_order.append(u)
            
            for v in sanitized.get(u, []):
                in_degree[v] -= 1
                depth_map[v] = max(depth_map[v], depth_map[u] + 1)
                if depth_map[v] > cls.MAX_DEPTH:
                    raise GraphValidationError(f"Profondità del grafo superiore al limite di {cls.MAX_DEPTH}")
                if in_degree[v] == 0:
                    queue.append(v)

        # Se l'ordine topologico non contiene tutti i nodi, c'è un ciclo
        if len(topo_order) != len(in_degree):
            raise GraphValidationError("Rilevato ciclo nel grafo delle dipendenze (Grafo non aciclico)")

        # Iniezione Late Integration Merge se frontend in STANDBY
        if frontend_status == "STANDBY":
            if "NK-App-UX-Architect" not in topo_order:
                topo_order.append("NK-App-UX-Architect")
            if "LATE_INTEGRATION_MERGE" not in topo_order:
                topo_order.append("LATE_INTEGRATION_MERGE")

        return topo_order

# -------------------------------------------------------------
# DependencyGraph using DFS (from Part 2)
# -------------------------------------------------------------
class DependencyGraph:
    def __init__(self, adj_list: Dict[str, List[str]]):
        self.adj_list = adj_list  # Nodo -> Nodi da cui dipende (genitori/dipendenze)

    def has_cycle(self) -> bool:
        """Rilevamento cicli tramite algoritmo DFS a tre colori (0=unvisited, 1=visiting, 2=visited)."""
        visited = {node: 0 for node in self.adj_list}
        
        # Aggiungiamo nodi mancanti nella lista di adiacenza
        for neighbors in self.adj_list.values():
            for n in neighbors:
                if n not in visited:
                    visited[n] = 0

        def dfs(node: str) -> bool:
            visited[node] = 1
            for neighbor in self.adj_list.get(node, []):
                if visited.get(neighbor, 0) == 1:
                    return True
                if visited.get(neighbor, 0) == 0:
                    if dfs(neighbor):
                        return True
            visited[node] = 2
            return False

        for node in list(visited.keys()):
            if visited[node] == 0:
                if dfs(node):
                    return True
        return False

    def topological_sort(self, target_nodes: Set[str]) -> List[str]:
        """Restituisce un ordinamento topologico dei soli nodi interessati e discendenti."""
        if self.has_cycle():
            raise CycleDetectedError("Rilevata dipendenza circolare nel grafo di sviluppo software. Impossibile procedere.")
        
        visited = set()
        order = []

        def visit(node: str):
            if node in visited:
                return
            visited.add(node)
            for neighbor in self.adj_list.get(node, []):
                visit(neighbor)
            order.append(node)

        for target in target_nodes:
            visit(target)
        
        return order

# -------------------------------------------------------------
# Async Runtime Non-Blocking Orchestrator
# -------------------------------------------------------------
class AsyncNonBlockingOrchestrator:
    def __init__(self, concurrency_limit: int, heartbeat_dir: str):
        self.semaphore = asyncio.Semaphore(concurrency_limit)
        self.heartbeat_dir = os.path.abspath(heartbeat_dir)
        os.makedirs(self.heartbeat_dir, exist_ok=True)

    async def run_node_agent(self, node_id: str, coro_task):
        """Esegue il nodo controllando i limiti di concorrenza senza bloccare gli altri thread."""
        async with self.semaphore:
            # Avvia la scrittura asincrona dell'heartbeat isolato in un task separato
            stop_heartbeat = asyncio.Event()
            heartbeat_task = asyncio.create_task(self._pulse_heartbeat(node_id, stop_heartbeat))
            
            try:
                result = await coro_task
                return result
            finally:
                stop_heartbeat.set()
                heartbeat_task.cancel()
                try:
                    await heartbeat_task
                except asyncio.CancelledError:
                    pass
                self._cleanup_heartbeat(node_id)

    async def _pulse_heartbeat(self, node_id: str, stop_event: asyncio.Event):
        """Aggiorna un file di heartbeat dedicato per evitare scritture concorrenti su index.yaml."""
        hb_file = os.path.join(self.heartbeat_dir, f"{node_id}.heartbeat")
        while not stop_event.is_set():
            try:
                with open(hb_file, 'w', encoding='utf-8') as f:
                    f.write(str(time.time()))
            except Exception:
                pass
            try:
                # Emette heartbeat ogni 15 secondi (attesa reattiva o cancellabile)
                await asyncio.sleep(15)
            except asyncio.CancelledError:
                break

    def _cleanup_heartbeat(self, node_id: str):
        hb_file = os.path.join(self.heartbeat_dir, f"{node_id}.heartbeat")
        if os.path.exists(hb_file):
            try:
                os.remove(hb_file)
            except Exception:
                pass

    def check_for_deadlocks(self, active_nodes: List[str], timeout_seconds: float = 90.0) -> List[str]:
        """Trova nodi in deadlock confrontando l'heartbeat isolato."""
        deadlocked_nodes = []
        now = time.time()
        for node_id in active_nodes:
            hb_file = os.path.join(self.heartbeat_dir, f"{node_id}.heartbeat")
            if os.path.exists(hb_file):
                try:
                    with open(hb_file, 'r', encoding='utf-8') as f:
                        last_hb = float(f.read().strip())
                    if now - last_hb > timeout_seconds:
                        deadlocked_nodes.append(node_id)
                except Exception:
                    pass
        return deadlocked_nodes
