jQuery(function () {
    //variables
    const board_sections = $(".board-sections");
    const pieces = $(".piece");
    const turn = $("#pl");

    // row column diagonal
    const row_1 = [];
    const row_2 = [];
    const row_3 = [];
    const row_4 = [];
    const col_1 = [];
    const col_2 = [];
    const col_3 = [];
    const col_4 = [];
    const di_1 = [];
    const di_2 = [];
    //
    //
    //
    ///////////////////turn text
    let counter = 2;
    board_sections.on("drop", function () {
        turn.text(`player-${counter}`).css("color", "gray");
        counter--;
        if (counter == 0) {
            counter = 2;
            turn.css("color", "white");
        }
    });
    //
    //
    //
    /////////////////////////////////////////// drag and drop functions //////////////////////////
    //
    //
    //
    pieces.draggable({
        drag: function (event, ui) {
            $(this).css("z-index", "100").css("cursor", "move");
        },
    });
    //
    //
    board_sections.droppable({
        tolerance: "intersect",
        drop: function (event, ui) {
            $(".pieces-container").remove($(ui.draggable)[0]);
            $(this).append($(ui.draggable)[0]);
            $(this)
                .children("div")
                .css("position", "absolute")
                .css("top", "50%")
                .css("left", "50%")
                .css("transform", "translate(-57.5% ,-57.5%)")
                .css("cursor", "move");

            //
            // stop drag and drop after dropped the piece
            $(ui.draggable[0]).draggable({
                disabled: true,
            });
            $(this).droppable({
                disabled: true,
            });
            //
            //
            //
            ///////////////////////////////////////////////  conditions /////////////////////////////////////////////
            //
            //
            //
            let section_id = $(this)[0].id;
            //
            if (section_id === "r1-c1" || section_id === "r1-c2" || section_id === "r1-c3" || section_id === "r1-c4") {
                row_1.push($(this)[0]);
            }
            if (section_id === "r2-c1" || section_id === "r2-c2" || section_id === "r2-c3" || section_id === "r2-c4") {
                row_2.push($(this)[0]);
            }
            if (section_id === "r3-c1" || section_id === "r3-c2" || section_id === "r3-c3" || section_id === "r3-c4") {
                row_3.push($(this)[0]);
            }
            if (section_id === "r4-c1" || section_id === "r4-c2" || section_id === "r4-c3" || section_id === "r4-c4") {
                row_4.push($(this)[0]);
            }
            //
            if (section_id === "r1-c1" || section_id === "r2-c1" || section_id === "r3-c1" || section_id === "r4-c1") {
                col_1.push($(this)[0]);
            }
            if (section_id === "r1-c2" || section_id === "r2-c2" || section_id === "r3-c2" || section_id === "r4-c2") {
                col_2.push($(this)[0]);
            }
            if (section_id === "r1-c3" || section_id === "r2-c3" || section_id === "r3-c3" || section_id === "r4-c3") {
                col_3.push($(this)[0]);
            }
            if (section_id === "r1-c4" || section_id === "r2-c4" || section_id === "r3-c4" || section_id === "r4-c4") {
                col_4.push($(this)[0]);
            }
            //
            if (section_id === "r1-c1" || section_id === "r2-c2" || section_id === "r3-c3" || section_id === "r4-c4") {
                di_1.push($(this)[0]);
            }
            if (section_id === "r1-c4" || section_id === "r2-c3" || section_id === "r3-c2" || section_id === "r4-c1") {
                di_2.push($(this)[0]);
            }
            //
            //
            //

            const selected_cube = new Set();
            const selected_cyl = new Set();
            const selected_big = new Set();
            const selected_small = new Set();
            const selected_dark = new Set();
            const selected_light = new Set();
            const selected_hole = new Set();
            const selected_solid = new Set();
            //
            //
            //
            function selector(arr) {
                if (arr.length == 4) {
                    arr.forEach((element) => {
                        if ($(element).children().hasClass("cube") && selected_cube.size < 5) {
                            selected_cube.add($(element).children()[0]);
                        }
                        if ($(element).children().hasClass("cyl") && selected_cyl.size < 5) {
                            selected_cyl.add($(element).children()[0]);
                        }
                        if ($(element).children().hasClass("big") && selected_big.size < 5) {
                            selected_big.add($(element).children()[0]);
                        }
                        if ($(element).children().hasClass("small") && selected_small.size < 5) {
                            selected_small.add($(element).children()[0]);
                        }
                        if ($(element).children().hasClass("dark") && selected_dark.size < 5) {
                            selected_dark.add($(element).children()[0]);
                        }
                        if ($(element).children().hasClass("light") && selected_light.size < 5) {
                            selected_light.add($(element).children()[0]);
                        }
                        if ($(element).children().hasClass("hole") && selected_hole.size < 5) {
                            selected_hole.add($(element).children()[0]);
                        }
                        if ($(element).children().hasClass("solid") && selected_solid.size < 5) {
                            selected_solid.add($(element).children()[0]);
                        }
                    });
                }
            }
            //
            selector(row_1);
            selector(row_2);
            selector(row_3);
            selector(row_4);
            selector(col_1);
            selector(col_2);
            selector(col_3);
            selector(col_4);
            selector(di_1);
            selector(di_2);
            //
            //
            //
            //////////////////////////////////////////////////// winner /////////////////////////////////////////
            //
            //
            //
            let winner = false;
            //
            function final_result(selector, attr) {
                if (selector.size === 4) {
                    winner = true;
                    selector.forEach((element) => {
                        $(element).parent().css("background-image", "url(/images/gray-velvet.webp)");
                        $(element).css("opacity", "0.6");
                        turn.text(`player-${counter} won by matching ${attr}'s`).css("text-decoration", "underline");
                    });
                    ////////////////////stop pieces to be draggable
                    pieces.draggable({
                        disabled: true,
                    });
                    //
                    //
                    //
                } else {
                    let zero = Array.from(selector);
                    zero.length = 0;
                    function findToRemove(arr) {
                        if (arr.length === 4 && winner !== true) {
                            arr.length = 0;
                        }
                    }

                    findToRemove(di_1);
                    findToRemove(di_2);
                    findToRemove(row_1);
                    findToRemove(row_2);
                    findToRemove(row_3);
                    findToRemove(row_4);
                    findToRemove(col_1);
                    findToRemove(col_2);
                    findToRemove(col_3);
                    findToRemove(col_4);
                }
            }
            //
            final_result(selected_cube, "shape");

            final_result(selected_cyl, "shape");

            final_result(selected_big, "size");

            final_result(selected_small, "size");

            final_result(selected_dark, "color");

            final_result(selected_light, "color");

            final_result(selected_hole, "face");

            final_result(selected_solid, "face");
        },
    });
});
