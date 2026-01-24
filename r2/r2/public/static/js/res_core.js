/* RES Core Features Integration */

(function() {
    // Wait for r.config to apply
    if (typeof r === 'undefined' || !r.config) return;

    // 1. Night Mode
    if (r.config.pref_nightmode) {
        document.body.classList.add('res-nightmode');
        // Add a simple style for it if not present (this serves as a baseline)
        const style = document.createElement('style');
        style.textContent = `
            body.res-nightmode { background-color: #222 !important; color: #ddd !important; }
            body.res-nightmode .thing, body.res-nightmode .entry { background-color: #333 !important; border-color: #444 !important; }
            body.res-nightmode .title a { color: #8ab6ff !important; }
            body.res-nightmode .md { color: #ccc !important; }
            body.res-nightmode header, body.res-nightmode #header { background-color: #1a1a1a !important; border-bottom: 1px solid #444 !important; }
            body.res-nightmode aside, body.res-nightmode .side { background-color: #2a2a2a !important; }
            body.res-nightmode .user-tag { background-color: #444; color: #fff; padding: 0 4px; border-radius: 3px; font-size: 0.8em; margin-left: 5px; border: 1px solid #666; }
            body.res-nightmode a { color: #5f99cf !important; }
        `;
        document.head.appendChild(style);
    }

    // 2. User Tagger and Enhancement Data
    let enhancements = {};
    try {
        enhancements = JSON.parse(r.config.pref_enhancement_json || '{}');
    } catch (e) {
        console.error('Failed to parse enhancement JSON', e);
    }

    const userTags = enhancements.user_tags || {};

    function applyUserTags() {
        if (Object.keys(userTags).length === 0) return;

        const authors = document.querySelectorAll('a.author');
        authors.forEach(authorLink => {
            const username = authorLink.textContent;
            if (userTags[username]) {
                // Check if already tagged
                if (authorLink.nextElementSibling && authorLink.nextElementSibling.classList.contains('user-tag')) return;

                const tagData = userTags[username];
                const tagSpan = document.createElement('span');
                tagSpan.className = 'user-tag';
                tagSpan.textContent = tagData.text || 'Tagged';
                if (tagData.color) {
                    tagSpan.style.backgroundColor = tagData.color;
                }
                
                authorLink.parentNode.insertBefore(tagSpan, authorLink.nextSibling);
            }
        });
    }

    // Apply on load
    applyUserTags();

    // Re-apply if content changes (e.g. infinite scroll)
    const observer = new MutationObserver((mutations) => {
        applyUserTags();
    });
    const siteTable = document.querySelector('#siteTable');
    if (siteTable) {
        observer.observe(siteTable, { childList: true, subtree: true });
    } else {
        // Fallback for generic body changes if siteTable isn't found
        observer.observe(document.body, { childList: true, subtree: true });
    }

    // 3. Image Expander (Basic)
    if (r.config.pref_show_images) {
        // Find links ending in jpg/png/gif
        const processImages = () => {
             const links = document.querySelectorAll('div.thing a.title');
             links.forEach(link => {
                if (link.dataset.processed) return;
                link.dataset.processed = "true";

                if (link.href.match(/\.(jpeg|jpg|gif|png)$/i)) {
                    // Create expand button
                    const btn = document.createElement('button');
                    btn.textContent = '+';
                    btn.className = 'expando-button collapsed'; 
                    btn.style.marginRight = '5px';
                    btn.style.cursor = 'pointer';
                    
                    btn.onclick = (e) => {
                        e.preventDefault();
                        e.stopPropagation();
                        // Toggle logic
                        if (btn.classList.contains('expanded')) {
                            // Collapse
                            if (link.nextElementSibling && link.nextElementSibling.classList.contains('res-image-preview')) {
                                link.nextElementSibling.style.display = 'none';
                            }
                            btn.textContent = '+';
                            btn.classList.remove('expanded');
                            btn.classList.add('collapsed');
                        } else {
                            // Expand
                            let imgInfo = link.nextElementSibling;
                            if (imgInfo && imgInfo.classList.contains('res-image-preview')) {
                                imgInfo.style.display = 'block';
                            } else {
                                const container = document.createElement('div');
                                container.className = 'res-image-preview';
                                container.style.marginTop = '10px';
                                container.style.maxWidth = '100%';
                                
                                const img = document.createElement('img');
                                img.src = link.href;
                                img.style.maxWidth = '100%';
                                img.style.display = 'block';
                                
                                container.appendChild(img);
                                link.parentNode.insertBefore(container, link.nextSibling);
                            }
                            btn.textContent = '-';
                            btn.classList.remove('collapsed');
                            btn.classList.add('expanded');
                        }
                    };
                    link.parentNode.insertBefore(btn, link);
                }
             });
        };
        
        processImages();
        
        if (siteTable) {
           const imgObserver = new MutationObserver(processImages);
           imgObserver.observe(siteTable, { childList: true, subtree: true });
        }
    }

    // Expose RES API for settings management
    window.RES = window.RES || {};
    
    // Function to save generic enhancements (User Tags, Dashboard state, etc)
    window.RES.saveSettings = function(newEnhancements) {
        const merged = { ...enhancements, ...newEnhancements };
        const formData = new FormData();
        formData.append('pref_enhancement_json', JSON.stringify(merged));
        formData.append('uh', r.config.modhash); 
        
        return fetch('/api/options', {
            method: 'POST',
            body: formData
        }).then(res => {
            if (res.ok) {
                enhancements = merged;
                console.log('RES Settings Saved');
                if (newEnhancements.user_tags) applyUserTags();
            } else {
                console.error('Failed to save RES settings');
            }
        });
    };
    
    // Simple toggle for Night Mode
    window.RES.toggleNightMode = function() {
        const newState = !r.config.pref_nightmode;
        const formData = new FormData();
        formData.append('pref_nightmode', newState);
        formData.append('uh', r.config.modhash);
        
        fetch('/api/options', {
            method: 'POST',
            body: formData
        }).then(res => {
             if (res.ok) window.location.reload();
        });
    };
    
    // Simple toggle for Image Expander
    window.RES.toggleImageExpander = function() {
        const newState = !r.config.pref_show_images;
        const formData = new FormData();
        formData.append('pref_show_images', newState);
        formData.append('uh', r.config.modhash);
        
        fetch('/api/options', {
             method: 'POST',
             body: formData
        }).then(res => {
              if (res.ok) window.location.reload();
        });
    };
    
    console.log('RES Core Loaded');

})();
