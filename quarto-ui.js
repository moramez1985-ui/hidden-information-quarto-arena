(() => {
    "use strict";

    const board = document.getElementById("board-grid");
    const piecesContainer = document.getElementById("pieces-container");
    const piecesCount = document.getElementById("pieces-count");
    const piecesHelp = document.getElementById("pieces-help");
    const modeSelect = document.getElementById("mode-select");
    const newGameButton = document.getElementById("new-game");
    const gameStatus = document.getElementById("game-status");
    const turnPiece = document.getElementById("turn-piece");
    const turnPieceLabel = document.getElementById("turn-piece-label");
    const turnPiecePreview = document.getElementById("turn-piece-preview");
    const winReason = document.getElementById("win-reason");
    const lastActionValue = document.getElementById("last-action");
    const lastMovePreview = document.getElementById("last-move-preview");
    const connectionError = document.getElementById("connection-error");
    const retryButton = document.getElementById("retry-state");
    const rulesText = document.getElementById("rules-text");

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

    function playerName(player) {
        return player === "player_1" ? "Player 1" : "Player 2";
    }

    function otherPlayer(player) {
        return player === "player_1" ? "player_2" : "player_1";
    }

    function createPieceIcon(piece, frameSize) {
        const svgNamespace = "http://www.w3.org/2000/svg";
        const svg = document.createElementNS(svgNamespace, "svg");
        const attributes = new Set(piece.attributes);
        const tall = attributes.has("big");
        const hollow = attributes.has("hole");
        const cylinder = attributes.has("cylinder");
        const topY = tall ? 30 : 42;
        const colors = attributes.has("light")
            ? { body: "#bb6b37", top: "#d89263", shade: "#98532f" }
            : { body: "#3f7652", top: "#75a17e", shade: "#315e41" };

        svg.setAttribute("class", "piece-icon");
        svg.setAttribute("viewBox", "0 0 64 64");
        svg.setAttribute("width", String(frameSize));
        svg.setAttribute("height", String(frameSize));
        svg.setAttribute("aria-hidden", "true");
        svg.setAttribute("focusable", "false");

        const addShape = (tagName, shapeAttributes) => {
            const shape = document.createElementNS(svgNamespace, tagName);
            for (const [name, value] of Object.entries(shapeAttributes)) {
                shape.setAttribute(name, String(value));
            }
            svg.append(shape);
        };

        if (cylinder) {
            addShape("ellipse", {
                cx: 32,
                cy: 55,
                rx: 22,
                ry: 8,
                fill: colors.shade,
            });
            addShape("path", {
                d: `M10 ${topY} V55 H54 V${topY} Z`,
                fill: colors.body,
            });
            addShape("path", {
                d: `M15 ${topY + 3} V52`,
                fill: "none",
                stroke: colors.top,
                "stroke-linecap": "round",
                "stroke-width": 2,
                opacity: 0.15,
            });
            addShape("ellipse", {
                cx: 32,
                cy: topY,
                rx: 22,
                ry: 8,
                fill: colors.top,
                stroke: colors.shade,
                "stroke-width": 1.5,
            });
        } else {
            addShape("path", {
                d: `M10 ${topY} L32 ${topY + 10} V58 L10 48 Z`,
                fill: colors.shade,
                stroke: colors.shade,
                "stroke-linejoin": "round",
                "stroke-width": 1,
            });
            addShape("path", {
                d: `M32 ${topY + 10} L54 ${topY} V48 L32 58 Z`,
                fill: colors.body,
                stroke: colors.shade,
                "stroke-linejoin": "round",
                "stroke-width": 1,
            });
            addShape("path", {
                d: `M10 ${topY} L32 ${topY - 10} L54 ${topY} L32 ${topY + 10} Z`,
                fill: colors.top,
                stroke: colors.shade,
                "stroke-linejoin": "round",
                "stroke-width": 1.5,
            });
        }

        if (hollow) {
            addShape("ellipse", {
                cx: 32,
                cy: cylinder ? topY : topY,
                rx: cylinder ? 9 : 7,
                ry: 4,
                fill: "var(--piece-hole)",
                stroke: colors.shade,
                "stroke-width": 1.2,
            });
        }

        return svg;
    }

    function turnInstruction() {
        if (!currentState) {
            return "Choose a mode and start a game.";
        }
        if (currentState.is_terminal) {
            return currentState.result.outcome === "win"
                ? `${playerName(currentState.result.winner)} wins.`
                : "Draw.";
        }

        const player = playerName(currentState.active_player);
        if (currentState.phase === "select") {
            if (currentState.mode === "classic") {
                return `${player}: choose a piece for ${playerName(otherPlayer(currentState.active_player))}.`;
            }
            return `${player}: choose your piece.`;
        }
        if (currentState.mode === "classic") {
            return `${player}: place this piece on an empty square.`;
        }
        return `${player}: place your piece on an empty square.`;
    }

    function winningLineLocation(cells) {
        const rows = new Set(cells.map((cell) => Math.floor(cell / 4)));
        if (rows.size === 1) {
            const row = [...rows][0];
            return row === 0 ? "top row" : row === 3 ? "bottom row" : `row ${row + 1}`;
        }

        const columns = new Set(cells.map((cell) => cell % 4));
        if (columns.size === 1) {
            const column = [...columns][0];
            return column === 0
                ? "left column"
                : column === 3
                    ? "right column"
                    : `column ${column + 1}`;
        }
        return "diagonal";
    }

    function readableAttribute(attribute) {
        const labels = {
            cube: "square",
            cylinder: "round",
            light: "light",
            dark: "dark",
            big: "large",
            small: "small",
            solid: "solid",
            hole: "hollow",
        };
        return labels[attribute] || null;
    }

    function winningReason() {
        const lines = currentState?.result?.winning_lines || [];
        return lines.map((line) => {
            const location = `the ${winningLineLocation(line.cells)}`;
            const attributes = line.shared_attributes
                .map(readableAttribute)
                .filter(Boolean);
            if (!attributes.length) {
                return `Four pieces in ${location} form a winning line.`;
            }
            const description = attributes.join(" and ");
            const shared = attributes.length === 1 ? "share an attribute" : "share these attributes";
            return `Four ${description} pieces in ${location} ${shared}.`;
        }).join(" ");
    }

    function previousSelectionFor(actionIndex) {
        for (let index = actionIndex; index >= 0; index -= 1) {
            const action = currentState.history[index];
            if (action.kind === "select_piece") {
                return action;
            }
        }
        return null;
    }

    function renderLastMove() {
        const history = currentState?.history || [];
        const actionIndex = history.length - 1;
        const action = history[actionIndex];
        lastMovePreview.replaceChildren();
        lastMovePreview.hidden = true;

        if (!action) {
            lastActionValue.textContent = "No moves yet";
            return;
        }

        const selection = action.kind === "select_piece"
            ? action
            : previousSelectionFor(actionIndex - 1);
        const piece = selection ? pieceForId(selection.piece_id) : null;
        if (piece) {
            lastMovePreview.append(createPieceIcon(piece, 24));
            lastMovePreview.hidden = false;
        }

        const actor = playerName(action.player);
        if (action.kind === "select_piece") {
            lastActionValue.textContent = currentState.mode === "classic"
                ? `${actor} chose a piece for ${playerName(otherPlayer(action.player))}.`
                : `${actor} chose a piece.`;
            return;
        }

        const row = Math.floor(action.cell / 4) + 1;
        const column = (action.cell % 4) + 1;
        lastActionValue.textContent = `${actor} placed a piece at row ${row}, column ${column}.`;
    }

    function renderBoard() {
        const placeableCells = new Set(
            currentState?.phase === "place" && legalActions?.type === "place_piece"
                ? legalActions.cells
                : [],
        );
        const winningCells = new Set(
            currentState?.result?.outcome === "win"
                ? currentState.result.winning_lines.flatMap((line) => line.cells)
                : [],
        );

        board.replaceChildren();
        for (let cell = 0; cell < 16; cell += 1) {
            const cellButton = document.createElement("button");
            const pieceId = currentState ? currentState.board[cell] : null;
            const canPlace = placeableCells.has(cell);

            cellButton.type = "button";
            cellButton.className = "board-cell";
            cellButton.dataset.cell = String(cell);
            cellButton.setAttribute("role", "gridcell");

            if (pieceId === null) {
                cellButton.classList.add("is-empty");
            } else {
                cellButton.classList.add("is-occupied");
                const piece = pieceForId(pieceId);
                if (piece) {
                    cellButton.append(createPieceIcon(piece, 42));
                }
            }

            if (canPlace) {
                cellButton.classList.add("is-legal");
                cellButton.addEventListener("click", () => submitPlacement(cell));
            }
            if (winningCells.has(cell)) {
                cellButton.classList.add("is-winning");
            }

            cellButton.disabled = !canPlace || busy || needsSync;
            cellButton.setAttribute(
                "aria-label",
                pieceId === null
                    ? `Cell ${cell + 1}${canPlace ? ", legal placement" : ", empty"}`
                    : `Cell ${cell + 1}, piece ${pieceId + 1}`,
            );
            board.append(cellButton);
        }
    }

    function renderPieces() {
        const remainingPieces = new Set(
            currentState ? currentState.remaining_pieces : pieces.map((piece) => piece.id),
        );
        const selectablePieces = new Set(
            currentState?.phase === "select" && legalActions?.type === "select_piece"
                ? legalActions.piece_ids
                : [],
        );
        const selectedId = currentState?.phase === "place"
            ? currentState.selected_piece
            : null;

        piecesContainer.replaceChildren();
        for (const piece of pieces) {
            if (!remainingPieces.has(piece.id)) {
                continue;
            }

            const selectable = selectablePieces.has(piece.id);
            const selected = selectedId === piece.id;
            const button = document.createElement("button");
            const idLabel = document.createElement("span");

            button.type = "button";
            button.className = "piece-button";
            button.setAttribute(
                "aria-label",
                `Piece ${piece.id + 1}: ${piece.attributes.join(", ")}`,
            );
            button.setAttribute("aria-pressed", String(selected));
            button.disabled = !selectable || busy || needsSync;
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

            button.append(createPieceIcon(piece, 32));
            idLabel.className = "piece-id";
            idLabel.textContent = `ID ${piece.id + 1}`;
            button.append(idLabel);
            piecesContainer.append(button);
        }

        piecesCount.textContent = String(remainingPieces.size);
        piecesHelp.textContent = currentState?.phase === "place" && !currentState.is_terminal
            ? "Choose an empty square on the board."
            : "Remaining pieces";
    }

    function renderTurnPiece() {
        turnPiecePreview.replaceChildren();
        const shouldShow = currentState?.phase === "place" && !currentState.is_terminal;
        const piece = shouldShow ? pieceForId(currentState.selected_piece) : null;
        turnPiece.hidden = !piece;
        if (!piece) {
            return;
        }

        turnPieceLabel.textContent = currentState.mode === "classic"
            ? `Piece for ${playerName(currentState.active_player)}`
            : "Your piece";
        turnPiecePreview.append(createPieceIcon(piece, 42));
    }

    function renderRules() {
        if (currentState?.mode === "classic") {
            rulesText.textContent =
                "In Classic, choose a piece for the other player to place. Four pieces sharing an attribute in a row, column or diagonal win.";
            return;
        }
        rulesText.textContent =
            "In Self selection, choose a piece and place it yourself. Four pieces sharing an attribute in a row, column or diagonal win.";
    }

    function renderResult() {
        winReason.hidden = true;
        winReason.textContent = "";
        gameStatus.classList.toggle("is-win", false);
        gameStatus.classList.toggle("is-draw", false);

        if (!currentState?.is_terminal) {
            gameStatus.textContent = turnInstruction();
            return;
        }

        if (currentState.result.outcome === "win") {
            gameStatus.textContent = `${playerName(currentState.result.winner)} wins.`;
            winReason.textContent = winningReason();
            winReason.hidden = !winReason.textContent;
            gameStatus.classList.add("is-win");
            return;
        }

        gameStatus.textContent = "Draw.";
        winReason.textContent = "The board is full.";
        winReason.hidden = false;
        gameStatus.classList.add("is-draw");
    }

    function render() {
        modeSelect.disabled = busy || needsSync;
        newGameButton.disabled = busy || needsSync;
        retryButton.hidden = !needsSync;
        retryButton.disabled = busy;
        retryButton.textContent = busy ? "Checking connection..." : "Retry connection";

        renderResult();
        renderTurnPiece();
        renderLastMove();
        renderBoard();
        renderPieces();
        renderRules();
    }

    function showError(message) {
        connectionError.textContent = message;
        connectionError.hidden = false;
    }

    function clearError() {
        connectionError.textContent = "";
        connectionError.hidden = true;
    }

    function acceptServerState(payload, syncMode = false) {
        currentState = payload.state;
        legalActions = payload.legal_actions;
        needsSync = false;
        if (syncMode && currentState) {
            modeSelect.value = currentState.mode;
        }
        render();
    }

    async function recoverAfterRequestError(message, syncMode = false) {
        busy = true;
        needsSync = true;
        render();
        showError(`${message} Checking the current game state; the action will not be resent.`);
        try {
            const payload = await requestJson("/api/state");
            acceptServerState(payload, syncMode);
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
        if (
            !currentState ||
            currentState.phase !== "place" ||
            !legalActions?.cells.includes(cell)
        ) {
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
            acceptServerState(payload, true);
        } catch (error) {
            await recoverAfterRequestError(error.message, true);
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
            acceptServerState(statePayload, true);
            clearError();
        } catch {
            needsSync = true;
            showError("Still unable to reach the local service. Check that it is running and retry.");
        } finally {
            busy = false;
            render();
        }
    }

    async function initialize() {
        busy = true;
        render();
        try {
            const [piecesPayload, statePayload] = await Promise.all([
                requestJson("/api/pieces"),
                requestJson("/api/state"),
            ]);
            pieces = piecesPayload.pieces;
            acceptServerState(statePayload, true);
            clearError();
        } catch {
            needsSync = true;
            showError("Cannot connect to the local service. Start it, then retry.");
        } finally {
            busy = false;
            render();
        }
    }

    newGameButton.addEventListener("click", startNewGame);
    retryButton.addEventListener("click", retryConnection);

    initialize();
})();
