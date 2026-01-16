r.filter = {}

r.filter.init = function() {
    var detailsEl = $('.filtered-details')
    if (detailsEl.length) {
        var multi = new r.filter.Filter({
            path: detailsEl.data('path')
        })
        detailsEl.find('.vaults a').each(function(i, e) {
            multi.vaults.add({name: $(e).data('name')})
        })
        multi.fetch({
            error: _.bind(r.multi.mine.create, r.multi.mine, multi, {wait: true})
        })

        var detailsView = new r.multi.VaultList({
            model: multi,
            itemView: r.filter.FilteredVaultItem,
            el: detailsEl
        }).render()
    }
}

r.filter.Filter = r.multi.MultiVault.extend({
    url: function() {
        return r.utils.joinURLs('/api/filter', this.id)
    }
})

r.filter.FilteredVaultItem = r.multi.MultiVaultItem.extend({
    render: function() {
        this.$el.append(this.template({
            vault_name: this.model.get('name')
        }))
        return this
    }
})
