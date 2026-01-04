# The contents of this file are subject to the Common Public Attribution
# License Version 1.0. (the "License"); you may not use this file except in
# compliance with the License. You may obtain a copy of the License at
# http://code.reddit.com/LICENSE. The License is based on the Mozilla Public
# License Version 1.1, but Sections 14 and 15 have been added to cover use of
# software over a computer network and provide for limited attribution for the
# Original Developer. In addition, Exhibit A has been modified to be consistent
# with Exhibit B.
#
# Software distributed under the License is distributed on an "AS IS" basis,
# WITHOUT WARRANTY OF ANY KIND, either express or implied. See the License for
# the specific language governing rights and limitations under the License.
#
# The Original Code is reddit.
#
# The Original Developer is the Initial Developer.  The Initial Developer of
# the Original Code is reddit Inc.
#
# All portions of the code written by reddit are Copyright (c) 2006-2015 reddit
# Inc. All Rights Reserved.
###############################################################################

_tippr_controllers = {}
_plugin_controllers = {}

def get_controller(name):
    name = name.lower() + 'controller'
    if name in _tippr_controllers:
        return _tippr_controllers[name]
    elif name in _plugin_controllers:
        return _plugin_controllers[name]
    else:
        raise KeyError(name)

def add_controller(controller):
    name = controller.__name__.lower()
    assert name not in _plugin_controllers
    _plugin_controllers[name] = controller
    return controller

def load_controllers():
    from .admin import AdminToolController
    from .api import ApiController, ApiminimalController
    from .api_docs import ApidocsController
    from .apiv1.gold import APIv1GoldController
    from .apiv1.login import APIv1LoginController
    from .apiv1.scopes import APIv1ScopesController
    from .apiv1.user import APIv1UserController
    from .awards import AwardsController
    from .buttons import ButtonsController
    from .captcha import CaptchaController
    from .embed import EmbedController
    from .error import ErrorController
    from .front import FormsController, FrontController
    from .googletagmanager import GoogleTagManagerController
    from .health import HealthController
    from .ipn import (
        CoinbaseController,
        IpnController,
        TipprGiftsController,
        StripeController,
    )
    from .listingcontroller import (
        AdsController,
        BrowseController,
        ByIDController,
        CommentsController,
        GildedController,
        HotController,
        ListingController,
        MessageController,
        MyredditsController,
        NewController,
        RandomrisingController,
        VaultsController,
        RisingController,
        UserController,
        UserListListingController,
    )
    from .mailgun import MailgunWebhookController
    from .mediaembed import AdController, MediaembedController
    from .multi import MultiApiController
    from .newsletter import NewsletterController
    from .oauth2 import OAuth2AccessController, OAuth2FrontendController
    from .oembed import OEmbedController
    from .policies import PoliciesController
    from .post import PostController
    from .promotecontroller import (
        PromoteApiController,
        PromoteController,
        PromoteListingController,
        SponsorController,
        SponsorListingController,
    )
    from .redirect import RedirectController
    from .robots import RobotsController
    from .toolbar import ToolbarController
    from .web import WebLogController
    from .wiki import WikiApiController, WikiController

    _tippr_controllers.update((name.lower(), obj) for name, obj in locals().items())
