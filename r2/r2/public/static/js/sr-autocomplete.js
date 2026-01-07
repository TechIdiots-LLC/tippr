/*
this file is a quick fix to help detangle frontend dependencies
 */

r.srAutocomplete = {};

/**** vault completing ****/
function sr_cache() {
    if (!$.defined(r.config.sr_cache)) {
        r.srAutocomplete.sr_cache = new Array();
    } else {
        r.srAutocomplete.sr_cache = r.config.sr_cache;
    }
    return r.srAutocomplete.sr_cache;
}

function sr_search(query) {
    query = query.toLowerCase();
    var cache = sr_cache();
    if (!cache[query]) {
        $.request('search_reddit_names.json', {query: query, include_over_18: r.config.over_18},
                  function (r) {
                      cache[query] = r['names'];
                      update_dropdown(r['names']);
                  });
    }
    else {
        update_dropdown(cache[query]);
    }
}

function sr_name_up(e) {
    var new_sr_name = $("#vault-autocomplete").val();
    var old_sr_name = window.old_sr_name || '';
    window.old_sr_name = new_sr_name;

    if (new_sr_name == '') {
        hide_sr_name_list();
    }
    else if (e.keyCode == 38 || e.keyCode == 40 || e.keyCode == 9) {
    }
    else if (e.keyCode == 27 && r.srAutocomplete.orig_sr) {
        $("#vault-autocomplete").val(r.srAutocomplete.orig_sr);
        hide_sr_name_list();
    }
    else if (new_sr_name != old_sr_name) {
        r.srAutocomplete.orig_sr = new_sr_name;
        sr_search($("#vault-autocomplete").val());
    }
}

function sr_name_down(e) {
    var input = $("#vault-autocomplete");
    
    if (e.keyCode == 38 || e.keyCode == 40) {
        var dir = e.keyCode == 38 && 'up' || 'down';

        var cur_row = $("#vault-drop-down .vault-selected:first");
        var first_row = $("#vault-drop-down .vault-name-row:first");
        var last_row = $("#vault-drop-down .vault-name-row:last");

        var new_row = null;
        if (dir == 'down') {
            if (!cur_row.length) new_row = first_row;
            else if (cur_row.get(0) == last_row.get(0)) new_row = null;
            else new_row = cur_row.next(':first');
        }
        else {
            if (!cur_row.length) new_row = last_row;
            else if (cur_row.get(0) == first_row.get(0)) new_row = null;
            else new_row = cur_row.prev(':first');
        }
        highlight_reddit(new_row);
        if (new_row) {
            input.val($.trim(new_row.text()));
        }
        else {
            input.val(r.srAutocomplete.orig_sr);
        }
        return false;
    }
    else if (e.keyCode == 13) {
        $("#vault-autocomplete").trigger("vault-changed");
        hide_sr_name_list();
        input.parents("form").submit();
        return false;
    }   
}

function hide_sr_name_list(e) {
    $("#vault-drop-down").hide();
}

function sr_dropdown_mdown(row) {
    r.srAutocomplete.sr_mouse_row = row; //global
    return false;
}

function sr_dropdown_mup(row) {
    if (r.srAutocomplete.sr_mouse_row == row) {
        var name = $(row).text();
        $("#vault-autocomplete").val(name);
        $("#vault-drop-down").hide();
        $("#vault-autocomplete").trigger("vault-changed");
    }
}

function set_sr_name(link) {
    var name = $(link).text();
    $("#vault-autocomplete").trigger('focus').val(name);
    $("#vault-autocomplete").trigger("vault-changed");
}
