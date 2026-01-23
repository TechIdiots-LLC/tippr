// Infinite Scroll & RES Integration (Prototyping)

document.addEventListener("DOMContentLoaded", function () {
    const contentDiv = document.querySelector(".content");
    const footer = document.querySelector(".footer-parent");
    let loading = false;
    let after = null;

    // Check if we are on a listing page by looking for the .thing elements
    if (document.querySelectorAll(".thing").length > 0) {
        
        // Find the 'next' button link to get the 'after' parameter
        const nextButton = document.querySelector(".next-button a");
        if (nextButton) {
            const urlParams = new URLSearchParams(nextButton.search);
            after = urlParams.get("after");
        }

        // Create a sentinel element for IntersectionObserver
        const sentinel = document.createElement("div");
        sentinel.id = "infinite-scroll-sentinel";
        sentinel.innerHTML = "<p style='text-align:center; padding: 20px;'>Loading more content...</p>";
        sentinel.style.display = "none";
        // Append to content div instead of main body
        if (contentDiv) {
            contentDiv.appendChild(sentinel);

            const observer = new IntersectionObserver((entries) => {
                if (entries[0].isIntersecting && !loading && after) {
                    loading = true;
                    sentinel.style.display = "block";
                    
                    // Fetch next page via AJAX
                    const currentUrl = new URL(window.location.href);
                    currentUrl.searchParams.set("after", after);
                    
                    fetch(currentUrl.toString())
                        .then(response => response.text())
                        .then(html => {
                            const parser = new DOMParser();
                            const doc = parser.parseFromString(html, "text/html");
                            
                            // Extract new things
                            const newThings = doc.querySelectorAll(".thing");
                            const newNextButton = doc.querySelector(".next-button a");
                            
                            if (newThings.length > 0) {
                                newThings.forEach(thing => {
                                    contentDiv.insertBefore(thing, sentinel);
                                    // Re-initialize any JS widgets if necessary
                                });
                            }
                            
                            // Update 'after' for next load
                            if (newNextButton) {
                                const newParams = new URLSearchParams(newNextButton.search);
                                after = newParams.get("after");
                            } else {
                                after = null; // No more pages
                                sentinel.innerHTML = "<p style='text-align:center; padding: 20px;'>No more content.</p>";
                            }
                            
                            loading = false;
                            if (after) sentinel.style.display = "none";
                        })
                        .catch(err => {
                            console.error("Infinite scroll error:", err);
                            loading = false;
                            sentinel.style.display = "none";
                        });
                }
            }, { rootMargin: "200px" });

            observer.observe(sentinel);
        }
    }
});
