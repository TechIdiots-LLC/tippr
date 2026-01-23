/*
this file is a quick fix to help detangle frontend dependencies
 */

r.vaultAutocomplete = {};

/**** vault completing ****/
function vault_cache() {
    if (!$.defined(r.config.vault_cache)) {
        r.vaultAutocomplete.vault_cache = new Array();
    } else {
        r.vaultAutocomplete.vault_cache = r.config.vault_cache;
    }
    return r.vaultAutocomplete.vault_cache;
}

function vault_search(query) {
    query = query.toLowerCase();
    var cache = vault_cache();
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

function vault_name_up(e) {
    var new_vault_name = $("#vault-autocomplete").val();
    var old_vault_name = window.old_vault_name || '';
    window.old_vault_name = new_vault_name;

    if (new_vault_name == '') {
        hide_vault_name_list();
    }
    else if (e.keyCode == 38 || e.keyCode == 40 || e.keyCode == 9) {
    }
    else if (e.keyCode == 27 && r.vaultAutocomplete.orig_vault) {
        $("#vault-autocomplete").val(r.vaultAutocomplete.orig_vault);
        hide_vault_name_list();
    }
    else if (new_vault_name != old_vault_name) {
        r.vaultAutocomplete.orig_vault = new_vault_name;
        vault_search($("#vault-autocomplete").val());
    }
}

function vault_name_down(e) {
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
        highlight_vault(new_row);
        if (new_row) {
            input.val($.trim(new_row.text()));
        }
        else {
            input.val(r.vaultAutocomplete.orig_vault);
        }
        return false;
    }
    else if (e.keyCode == 13) {
        $("#vault-autocomplete").trigger("vault-changed");
        hide_vault_name_list();
        input.parents("form").submit();
        return false;
    }   
}

function hide_vault_name_list(e) {
    $("#vault-drop-down").hide();
}

function vault_dropdown_mdown(row) {
    r.vaultAutocomplete.vault_mouse_row = row; //global
    return false;
}

function vault_dropdown_mup(row) {
    if (r.vaultAutocomplete.vault_mouse_row == row) {
        var name = $(row).text();
        $("#vault-autocomplete").val(name);
        $("#vault-drop-down").hide();
        $("#vault-autocomplete").trigger("vault-changed");
    }
}

function set_vault_name(link) {
    var name = $(link).text();
    $("#vault-autocomplete").trigger('focus').val(name);
    $("#vault-autocomplete").trigger("vault-changed");
}
