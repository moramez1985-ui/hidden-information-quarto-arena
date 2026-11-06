(() => {
    "use strict";

    const board = document.getElementById("board-grid");
    const piecesContainer = document.getElementById("pieces-container");
    const selectedPieceContainer = document.getElementById("selected-piece");
    const modeSelect = document.getElementById("mode-select");
    const newGameButton = document.getElementById("new-game");
    const gameStatus = document.getElementById("game-status");
    const connectionError = document.getElementById("connection-error");
    const retryButton = document.getElementById("retry-state");

    let pieces = [];
    let currentState = null;
    let legalActions = null;
    let busy = false;
    let needsSync = false;

    class ApiError extends Error {
        constructor(message, status) {
            super(message);
            this.status = status;
        }
    }

    async function requestJson(path, options = {}) {
        const response = await fetch(path, {
            cache: "no-store",
            ...options,
            headers: {
                ...(options.headers || {}),
                ...(options.body ? { "Content-Type": "application/json" } : {}),
            },
        });
        let payload;
        try {
            payload = await response.json();
        } catch {
            throw new ApiError("The local service returned an unreadable response.", response.status);
        }
        if (!response.ok) {
            throw new ApiError(
                payload?.error?.message || `The local service returned HTTP ${response.status}.`,
                response.status,
            );
        }
        return payload;
    }

    function pieceForId(pieceId) {
        return pieces.find((piece) => piece.id === pieceId);
    }

    function pieceLabel(piece) {
        return piece.attributes.join(", ");
    }

    function addPieceClasses(element, piece) {
        element.classList.add("piece");
        for (const attribute of piece.attributes) {
            element.classList.add(attribute === "cylinder" ? "cyl" : attribute);
        }
    }

    function makePieceElement(piece, { selectable, selected, draggable }) {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "piece-button";
        button.dataset.pieceId = String(piece.id);
        button.setAttribute("aria-label", `Piece ${piece.id + 1}: ${pieceLabel(piece)}`);
        button.setAttribute("aria-pressed", String(selected));

        const shape = document.createElement("span");
        addPieceClasses(shape, piece);
        shape.setAttribute("aria-hidden", "true");
        button.append(shape);
        button.disabled = (!selectable && !draggable) || busy || needsSync;

        if (draggable) {
            button.draggable = !busy && !needsSync;
            button.classList.add("draggable-piece");
            button.addEventListener("dragstart", (event) => {
                if (busy || needsSync || !currentState || currentState.phase !== "place") {
                    event.preventDefault();
                    return;
                }
                event.dataTransfer.setData("text/plain", String(piece.id));
                event.dataTransfer.effectAllowed = "move";
            });
        }

        if (selectable) {
            button.addEventListener("click", () => {
                submitAction({
                    kind: "select_piece",
                    player: currentState.active_player,
                    piece_id: piece.id,
                    cell: null,
                });
            });
        }
        return button;
    }

    function render() {
        const isGameActive = Boolean(currentState);
        const isSelecting = isGameActive && currentState.phase === "select";
        const isPlacing = isGameActive && currentState.phase === "place";
        const isTerminal = isGameActive && currentState.is_terminal;
        const placeableCells = new Set(
            isPlacing && legalActions?.type === "place_piece" ? legalActions.cells : [],
        );
        const winningCells = new Map();

        if (isTerminal && currentState.result?.outcome === "win") {
            for (const line of currentState.result.winning_lines) {
                for (const cell of line.cells) {
                    const attributes = winningCells.get(cell) || new Set();
                    for (const attribute of line.shared_attributes) {
                        attributes.add(attribute);
                    }
                    winningCells.set(cell, attributes);
                }
            }
        }

        board.replaceChildren();
        for (let cell = 0; cell < 16; cell += 1) {
            const cellButton = document.createElement("button");
            cellButton.type = "button";
            cellButton.className = "board-sections";
            cellButton.setAttribute("role", "gridcell");
            cellButton.dataset.cell = String(cell);

            const pieceId = isGameActive ? currentState.board[cell] : null;
            if (pieceId !== null) {
                const piece = pieceForId(pieceId);
                if (piece) {
                    const shape = document.createElement("span");
                    addPieceClasses(shape, piece);
                    shape.setAttribute("aria-hidden", "true");
                    cellButton.append(shape);
                }
            } else {
                cellButton.textContent = "+";
            }

            const winningAttributes = winningCells.get(cell);
            if (winningAttributes) {
                cellButton.classList.add("winning-cell");
                cellButton.title = `Winning attributes: ${Array.from(winningAttributes).join(", ")}`;
            }

            const canPlace = placeableCells.has(cell);
            cellButton.disabled = !canPlace || busy || needsSync;
            cellButton.setAttribute("aria-label", pieceId === null
                ? `Cell ${cell + 1}${canPlace ? ", legal placement" : ""}`
                : `Cell ${cell + 1}, piece ${pieceId + 1}`);
            if (canPlace) {
                cellButton.addEventListener("click", () => submitPlacement(cell));
                cellButton.addEventListener("dragover", (event) => {
                    if (currentState?.phase === "place" && !busy && !needsSync) {
                        event.preventDefault();
                        event.dataTransfer.dropEffect = "move";
                    }
                });
                cellButton.addEventListener("drop", (event) => {
                    event.preventDefault();
                    if (
                        !busy &&
                        !needsSync &&
                        currentState?.phase === "place" &&
                        event.dataTransfer.getData("text/plain") === String(currentState.selected_piece)
                    ) {
                        submitPlacement(cell);
                    }
                });
            }
            board.append(cellButton);
        }

        piecesContainer.replaceChildren();
        const remaining = new Set(isGameActive ? currentState.remaining_pieces : []);
        const selectablePieces = new Set(
            isSelecting && legalActions?.type === "select_piece" ? legalActions.piece_ids : [],
        );
        for (const piece of pieces) {
            if (isGameActive && !remaining.has(piece.id)) {
                continue;
            }
            const isSelected = isPlacing && currentState.selected_piece === piece.id;
            piecesContainer.append(makePieceElement(piece, {
                selectable: selectablePieces.has(piece.id),
                selected: isSelected,
                draggable: isSelected,
            }));
        }

        selectedPieceContainer.replaceChildren();
        if (isPlacing) {
            const selectedPiece = pieceForId(currentState.selected_piece);
            if (selectedPiece) {
                selectedPieceContainer.textContent =
                    `Selected piece for placement: ${pieceLabel(selectedPiece)}`;
            }
        }

        modeSelect.disabled = busy || needsSync;
        newGameButton.disabled = busy || needsSync;
        newGameButton.textContent = isGameActive ? "New Game" : "Start game";
        retryButton.hidden = !needsSync;
        retryButton.disabled = busy;
        retryButton.textContent = busy ? "Checking connection..." : "Retry connection";

        if (!isGameActive) {
            gameStatus.textContent = "Choose a mode and start a game.";
        } else if (isTerminal) {
            const result = currentState.result;
            if (result.outcome === "win") {
                const lines = result.winning_lines.length;
                const attributes = Array.from(new Set(
                    result.winning_lines.flatMap((line) => line.shared_attributes),
                )).join(", ");
                gameStatus.textContent =
                    `${result.winner} wins in ${currentState.mode}! ${lines} winning line(s); ` +
                    `shared attributes: ${attributes}.`;
            } else {
                gameStatus.textContent = `Draw in ${currentState.mode}: the board is full.`;
            }
        } else if (currentState.phase === "select") {
            gameStatus.textContent = currentState.mode === "classic"
                ? `${currentState.mode}: ${currentState.active_player} chooses a piece for the other player.`
                : `${currentState.mode}: ${currentState.active_player} chooses a piece and will place it.`;
        } else {
            gameStatus.textContent = currentState.mode === "classic"
                ? `${currentState.mode}: ${currentState.active_player} places the piece chosen by ${currentState.selected_by}.`
                : `${currentState.mode}: ${currentState.active_player} places their selected piece.`;
        }
    }

    function showError(message) {
        connectionError.textContent = message;
        connectionError.hidden = false;
    }

    function clearError() {
        connectionError.textContent = "";
        connectionError.hidden = true;
    }

    function acceptServerState(payload) {
        currentState = payload.state;
        legalActions = payload.legal_actions;
        needsSync = false;
        if (currentState) {
            modeSelect.value = currentState.mode;
        }
        render();
    }

    async function refreshState() {
        const payload = await requestJson("/api/state");
        acceptServerState(payload);
    }

    async function recoverAfterRequestError(message) {
        busy = true;
        needsSync = true;
        render();
        showError(`${message} Checking the current game state; the action will not be resent.`);
        try {
            const payload = await requestJson("/api/state");
            acceptServerState(payload);
            showError(`${message} The displayed board has been refreshed from the server.`);
        } catch {
            needsSync = true;
            render();
            showError(`${message} The server state could not be confirmed. Retry connection before continuing.`);
        } finally {
            busy = false;
            render();
        }
    }

    async function submitAction(action) {
        if (busy || needsSync || !currentState) {
            return;
        }
        busy = true;
        clearError();
        render();
        try {
            const payload = await requestJson("/api/actions", {
                method: "POST",
                body: JSON.stringify(action),
            });
            acceptServerState(payload);
        } catch (error) {
            await recoverAfterRequestError(error.message);
        } finally {
            busy = false;
            render();
        }
    }

    function submitPlacement(cell) {
        if (!currentState || currentState.phase !== "place" || !legalActions?.cells.includes(cell)) {
            return;
        }
        submitAction({
            kind: "place_piece",
            player: currentState.active_player,
            piece_id: null,
            cell,
        });
    }

    async function startNewGame() {
        if (busy || needsSync) {
            return;
        }
        busy = true;
        clearError();
        render();
        try {
            const payload = await requestJson("/api/games", {
                method: "POST",
                body: JSON.stringify({ mode: modeSelect.value }),
            });
            acceptServerState(payload);
        } catch (error) {
            await recoverAfterRequestError(error.message);
        } finally {
            busy = false;
            render();
        }
    }

    async function retryConnection() {
        if (busy) {
            return;
        }
        busy = true;
        render();
        try {
            const [statePayload, piecesPayload] = await Promise.all([
                requestJson("/api/state"),
                requestJson("/api/pieces"),
            ]);
            pieces = piecesPayload.pieces;
            acceptServerState(statePayload);
            clearError();
        } catch {
            needsSync = true;
            showError("Still unable to reach the local service. Check that it is running and retry.");
        } finally {
            busy = false;
            render();
        }
    }

    newGameButton.addEventListener("click", startNewGame);
    retryButton.addEventListener("click", retryConnection);

    async function initialize() {
        busy = true;
        render();
        try {
            const [piecesPayload, statePayload] = await Promise.all([
                requestJson("/api/pieces"),
                requestJson("/api/state"),
            ]);
            pieces = piecesPayload.pieces;
            acceptServerState(statePayload);
            clearError();
        } catch {
            needsSync = true;
            showError("Cannot connect to the local game service. Start it, then retry.");
        } finally {
            busy = false;
            render();
        }
    }

    initialize();
})();
