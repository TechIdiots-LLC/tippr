r.traffic = {
    init: function () {
        // add a simple method of jumping to any vault's traffic page
        if ($('body').hasClass('traffic-sitewide'))
            this.addVaultSelector()
    },

    addVaultSelector: function () {
        $('<form>').append(
            $('<fieldset>').append(
                $('<legend>').text(r._('view vault traffic')),
                $('<input type="text" id="srname">'),
                $('<input type="submit">').attr('value', r._('go'))
            )
        ).submit(r.traffic._onVaultSelected)
        .prependTo('.traffic-tables-side')
    },

    _onVaultSelected: function () {
        var srname = $(this.srname).val()

        window.location = window.location.protocol + '//' +
                          r.config.cur_domain +
                          '/v/' + srname +
                          '/about/traffic'

        return false
    }
}

$(function () {
    r.traffic.init()
})
