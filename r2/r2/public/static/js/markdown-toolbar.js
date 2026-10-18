// The contents of this file are subject to the Common Public Attribution
// License Version 1.0 (the "License"); you may not use this file except in
// compliance with the License. You may obtain a copy of the License at
// https://github.com/TechIdiots-LLC/tippr/blob/master/LICENSE.
//
// Software distributed under the License is distributed on an "AS IS" basis,
// WITHOUT WARRANTY OF ANY KIND, either express or implied. See the License for
// the specific language governing rights and limitations under the License.
//
// The Original Code is Tippr.
//
// The Initial Developer of the Original Code is TechIdiots LLC.
// Copyright (c) 2026 TechIdiots LLC. All Rights Reserved.
///////////////////////////////////////////////////////////////////////////////

/*
 * Formatting toolbar, emoji picker and preview for the markdown text boxes
 * (comments, self posts, messages). The buttons only insert markdown into
 * the textarea; what is saved and how it is rendered doesn't change.
 * Typed :shortcodes: (e.g. :thumbsup:) become emoji when the text is
 * rendered (r2.lib.filters.emojify_html).
 */
r.markdownToolbar = {}

// [category, [[emoji, shortcode, other names], ...]], generated from the
// emoji package so the names match the server's shortcodes
r.markdownToolbar.emoji =[["smileys",[["😀","grinning","grinning_face"],["😃","smiley","grinning_face_with_big_eyes"],["😄","smile","grinning_face_with_smiling_eyes"],["😁","grin","beaming_face_with_smiling_eyes"],["😆","laughing","satisfied grinning_squinting_face"],["😅","sweat_smile","grinning_face_with_sweat"],["😂","joy","face_with_tears_of_joy"],["🤣","rofl","rolling_on_the_floor_laughing"],["🙂","slightly_smiling_face",""],["🙃","upside_down_face","upside-down_face"],["😉","wink","winking_face"],["😊","blush","smiling_face_with_smiling_eyes"],["😇","innocent","smiling_face_with_halo"],["🥰","smiling_face_with_hearts","smiling_face_with_three_hearts"],["😍","heart_eyes","smiling_face_with_heart-eyes smiling_face_with_heart_eyes"],["🤩","star-struck","star_struck"],["😘","kissing_heart","face_blowing_a_kiss"],["😋","yum","face_savoring_food"],["😛","stuck_out_tongue","face_with_tongue"],["😜","winking_face_with_tongue","stuck_out_tongue_winking_eye"],["🤪","zany_face",""],["😝","squinting_face_with_tongue","stuck_out_tongue_closed_eyes"],["🤑","money-mouth_face","money_mouth_face"],["🤗","hugs","hugging_face smiling_face_with_open_hands"],["🤭","hand_over_mouth","face_with_hand_over_mouth"],["🤫","shushing_face",""],["🤔","thinking","thinking_face"],["🤐","zipper_mouth_face","zipper-mouth_face"],["🤨","raised_eyebrow","face_with_raised_eyebrow"],["😐","neutral_face",""],["😑","expressionless","expressionless_face"],["😶","no_mouth","face_without_mouth"],["😏","smirk","smirking_face"],["😒","unamused","unamused_face"],["🙄","roll_eyes","face_with_rolling_eyes"],["😬","grimacing","grimacing_face"],["😌","relieved","relieved_face"],["😔","pensive","pensive_face"],["😪","sleepy","sleepy_face"],["🤤","drooling_face",""],["😴","sleeping","sleeping_face"],["😷","mask","face_with_medical_mask"],["🤒","face_with_thermometer",""],["🤕","face_with_head-bandage","face_with_head_bandage"],["🤢","nauseated_face",""],["🤮","face_vomiting","vomiting_face"],["🥵","hot_face",""],["🥶","cold_face",""],["🥴","woozy_face",""],["😵","dizzy_face","knocked_out_face face_with_crossed-out_eyes face_with_crossed_out_eyes"],["🤯","exploding_head",""],["🤠","cowboy_hat_face",""],["🥳","partying_face",""],["😎","sunglasses","smiling_face_with_sunglasses"],["🤓","nerd_face",""],["🧐","monocle_face","face_with_monocle"],["😕","confused","confused_face"],["😟","worried","worried_face"],["🙁","slightly_frowning_face",""],["😮","open_mouth","face_with_open_mouth"],["😯","hushed","hushed_face"],["😲","astonished","astonished_face"],["😳","flushed","flushed_face"],["🥺","pleading_face",""],["😦","frowning","frowning_face_with_open_mouth"],["😧","anguished","anguished_face"],["😨","fearful","fearful_face"],["😰","cold_sweat","anxious_face_with_sweat"],["😥","sad_but_relieved_face","disappointed_relieved"],["😢","cry","crying_face"],["😭","sob","loudly_crying_face"],["😱","scream","face_screaming_in_fear"],["😖","confounded","confounded_face"],["😣","persevere","persevering_face"],["😞","disappointed","disappointed_face"],["😓","sweat","downcast_face_with_sweat"],["😩","weary","weary_face"],["😫","tired_face",""],["🥱","yawning_face",""],["😤","triumph","face_with_steam_from_nose"],["😡","pout","rage enraged_face"],["😠","angry","angry_face"],["🤬","cursing_face","face_with_symbols_on_mouth"],["😈","smiling_imp","smiling_face_with_horns"],["💀","skull",""],["💩","shit","poop hankey pile_of_poo"],["🤡","clown_face",""],["👻","ghost",""],["👽","alien",""],["🤖","robot","robot_face"]]],["people",[["👋","wave","waving_hand"],["🤚","raised_back_of_hand",""],["✋","hand","raised_hand"],["🖖","vulcan_salute","raised_hand_with_part_between_middle_and_ring_fingers"],["👌","ok_hand",""],["🤌","pinched_fingers",""],["🤏","pinching_hand",""],["✌️","v","victory_hand"],["🤞","crossed_fingers",""],["🤟","love-you_gesture","love_you_gesture"],["🤘","metal","sign_of_the_horns"],["🤙","call_me_hand",""],["👈","point_left","backhand_index_pointing_left"],["👉","point_right","backhand_index_pointing_right"],["👆","point_up_2","backhand_index_pointing_up"],["👇","point_down","backhand_index_pointing_down"],["☝️","point_up","index_pointing_up"],["👍","+1","thumbsup thumbs_up"],["👎","_1","-1 thumbsdown thumbs_down"],["✊","fist","fist_raised raised_fist"],["👊","punch","facepunch fist_oncoming oncoming_fist"],["🤛","fist_left","left-facing_fist left_facing_fist"],["🤜","fist_right","right-facing_fist right_facing_fist"],["👏","clap","clapping_hands"],["🙌","raised_hands","raising_hands"],["👐","open_hands",""],["🤲","palms_up_together",""],["🤝","handshake",""],["🙏","pray","folded_hands"],["✍️","writing_hand",""],["💪","muscle","flexed_biceps"],["🧠","brain",""],["👀","eyes",""],["👁️","eye",""],["👅","tongue",""],["👄","lips","mouth"],["🤷","shrug","person_shrugging"],["🤦","facepalm","person_facepalming"],["🙋","raising_hand","person_raising_hand"],["🙇","bow","person_bowing"],["💁","tipping_hand_person","person_tipping_hand information_desk_person"],["🙅","no_good","person_gesturing_no"],["🙆","ok_person","person_gesturing_ok"],["🧑‍💻","technologist",""],["🕺","man_dancing",""],["💃","dancer","woman_dancing"]]],["hearts",[["❤️","heart","red_heart"],["🧡","orange_heart",""],["💛","yellow_heart",""],["💚","green_heart",""],["💙","blue_heart",""],["💜","purple_heart",""],["🖤","black_heart",""],["🤍","white_heart",""],["🤎","brown_heart",""],["💔","broken_heart",""],["❣️","heart_exclamation","heavy_heart_exclamation heavy_heart_exclamation_mark_ornament"],["💕","two_hearts",""],["💞","revolving_hearts",""],["💓","heartbeat","beating_heart"],["💗","heartpulse","growing_heart"],["💖","sparkling_heart",""],["💘","cupid","heart_with_arrow"],["💝","gift_heart","heart_with_ribbon"],["💯","100","hundred_points"],["💢","anger","anger_symbol"],["💥","boom","collision"],["💫","dizzy",""],["💦","sweat_drops","sweat_droplets"],["💨","dash","dashing_away"],["🕳️","hole",""],["💬","speech_balloon",""],["💭","thought_balloon",""],["💤","zzz",""]]],["nature",[["🐶","dog","dog_face"],["🐱","cat","cat_face"],["🐭","mouse","mouse_face"],["🐹","hamster",""],["🐰","rabbit","rabbit_face"],["🦊","fox","fox_face"],["🐻","bear",""],["🐼","panda","panda_face"],["🐨","koala",""],["🐯","tiger","tiger_face"],["🦁","lion","lion_face"],["🐮","cow","cow_face"],["🐷","pig","pig_face"],["🐸","frog",""],["🐵","monkey_face",""],["🙈","see_no_evil","see_no_evil_monkey see-no-evil_monkey"],["🙉","hear_no_evil","hear-no-evil_monkey hear_no_evil_monkey"],["🙊","speak_no_evil","speak-no-evil_monkey speak_no_evil_monkey"],["🐔","chicken",""],["🐧","penguin",""],["🐦","bird",""],["🦆","duck",""],["🦉","owl",""],["🦇","bat",""],["🐺","wolf",""],["🐴","horse","horse_face"],["🦄","unicorn","unicorn_face"],["🐝","bee","honeybee"],["🐛","bug",""],["🦋","butterfly",""],["🐌","snail",""],["🐞","beetle","lady_beetle"],["🐢","turtle",""],["🐍","snake",""],["🦖","t-rex","t_rex"],["🐙","octopus",""],["🦑","squid",""],["🦀","crab",""],["🐠","tropical_fish",""],["🐬","dolphin","flipper"],["🐳","whale","spouting_whale"],["🦈","shark",""],["🐊","crocodile",""],["🌵","cactus",""],["🌲","evergreen_tree",""],["🌴","palm_tree",""],["🌱","seedling",""],["🍀","four_leaf_clover",""],["🍁","maple_leaf",""],["🍂","fallen_leaf",""],["🌷","tulip",""],["🌹","rose",""],["🌻","sunflower",""],["🌸","cherry_blossom",""],["🌞","sun_with_face",""],["🌝","full_moon_face","full_moon_with_face"],["🌚","new_moon_face","new_moon_with_face"],["🌙","crescent_moon",""],["⭐","star",""],["🌟","star2","glowing_star"],["✨","sparkles",""],["⚡","zap","high_voltage"],["🔥","fire",""],["🌈","rainbow",""],["☀️","sun","sunny"],["⛅","partly_sunny","sun_behind_cloud"],["☁️","cloud",""],["🌧️","cloud_with_rain",""],["⛈️","thunder_cloud_and_rain","cloud_with_lightning_and_rain"],["❄️","snowflake",""],["☃️","snowman","snowman_with_snow"],["🌊","ocean","water_wave"]]],["food",[["🍏","green_apple",""],["🍎","apple","red_apple"],["🍐","pear",""],["🍊","orange","mandarin tangerine"],["🍋","lemon",""],["🍌","banana",""],["🍉","watermelon",""],["🍇","grapes",""],["🍓","strawberry",""],["🫐","blueberries",""],["🍒","cherries",""],["🍑","peach",""],["🥭","mango",""],["🍍","pineapple",""],["🥥","coconut",""],["🥝","kiwi_fruit",""],["🍅","tomato",""],["🥑","avocado",""],["🍆","eggplant",""],["🥔","potato",""],["🥕","carrot",""],["🌽","corn","ear_of_corn"],["🌶️","hot_pepper",""],["🥦","broccoli",""],["🍄","mushroom",""],["🥜","peanuts",""],["🍞","bread",""],["🥐","croissant",""],["🥨","pretzel",""],["🧀","cheese","cheese_wedge"],["🥚","egg","egg2"],["🍳","egg","cooking fried_egg"],["🥓","bacon",""],["🥩","cut_of_meat",""],["🍗","poultry_leg",""],["🍖","meat_on_bone",""],["🌭","hotdog","hot_dog"],["🍔","hamburger",""],["🍟","fries","french_fries"],["🍕","pizza",""],["🌮","taco",""],["🌯","burrito",""],["🥗","green_salad",""],["🍝","spaghetti",""],["🍜","ramen","steaming_bowl"],["🍣","sushi",""],["🍤","fried_shrimp",""],["🍩","doughnut",""],["🍪","cookie",""],["🎂","birthday","birthday_cake"],["🍰","cake","shortcake"],["🧁","cupcake",""],["🍫","chocolate_bar",""],["🍬","candy",""],["🍭","lollipop",""],["🍿","popcorn",""],["☕","coffee","hot_beverage"],["🍵","tea","teacup_without_handle"],["🧃","beverage_box",""],["🥤","cup_with_straw",""],["🍺","beer","beer_mug"],["🍻","beers","clinking_beer_mugs"],["🥂","clinking_glasses",""],["🍷","wine_glass",""],["🍸","cocktail","cocktail_glass"],["🍹","tropical_drink",""]]],["activity",[["⚽","soccer","soccer_ball"],["🏀","basketball",""],["🏈","football","american_football"],["⚾","baseball",""],["🎾","tennis",""],["🏐","volleyball",""],["🏉","rugby_football",""],["🎱","8ball","pool_8_ball"],["🏓","ping_pong","table_tennis_paddle_and_ball"],["🏸","badminton","badminton_racquet_and_shuttlecock"],["🥅","goal_net",""],["🏒","ice_hockey","ice_hockey_stick_and_puck"],["⛳","golf","flag_in_hole"],["🏹","bow_and_arrow",""],["🎣","fishing_pole","fishing_pole_and_fish"],["🥊","boxing_glove",""],["🥋","martial_arts_uniform",""],["⛸️","ice_skate",""],["🎿","ski","skis"],["🏂","snowboarder",""],["🏋️","weight_lifter","weight_lifting person_lifting_weights"],["🚴","bicyclist","person_biking"],["🏆","trophy",""],["🥇","1st_place_medal",""],["🥈","2nd_place_medal",""],["🥉","3rd_place_medal",""],["🏅","sports_medal","medal_sports"],["🎖️","military_medal","medal_military"],["🎗️","reminder_ribbon",""],["🎫","ticket",""],["🎟️","tickets","admission_tickets"],["🎪","circus_tent",""],["🎭","performing_arts",""],["🎨","art","artist_palette"],["🎬","clapper","clapper_board"],["🎤","microphone",""],["🎧","headphone","headphones"],["🎼","musical_score",""],["🎹","musical_keyboard",""],["🥁","drum",""],["🎷","saxophone",""],["🎺","trumpet",""],["🎸","guitar",""],["🎻","violin",""],["🎲","game_die",""],["♟️","chess_pawn",""],["🎯","dart","bullseye"],["🎳","bowling",""],["🎮","video_game",""],["🕹️","joystick",""],["🧩","jigsaw","puzzle_piece"]]],["objects",[["⌚","watch",""],["📱","iphone","mobile_phone"],["💻","laptop","computer"],["⌨️","keyboard",""],["🖥️","desktop_computer",""],["🖨️","printer",""],["🖱️","computer_mouse","three_button_mouse"],["💾","floppy_disk",""],["💿","cd","optical_disk"],["📷","camera",""],["📸","camera_flash","camera_with_flash"],["📹","video_camera",""],["🎥","movie_camera",""],["📞","telephone_receiver",""],["☎️","phone","telephone"],["📺","tv","television"],["📻","radio",""],["🎙️","studio_microphone",""],["⏰","alarm_clock",""],["⌛","hourglass","hourglass_done"],["⏳","hourglass_not_done","hourglass_flowing_sand"],["📡","satellite","satellite_antenna"],["🔋","battery",""],["🔌","electric_plug",""],["💡","bulb","light_bulb"],["🔦","flashlight",""],["🕯️","candle",""],["💸","money_with_wings",""],["💵","dollar","dollar_banknote"],["💰","moneybag","money_bag"],["💳","credit_card",""],["💎","gem","gem_stone"],["⚖️","scales","balance_scale"],["🔧","wrench",""],["🔨","hammer",""],["⚒️","hammer_and_pick",""],["🛠️","hammer_and_wrench",""],["⚙️","gear",""],["🔩","nut_and_bolt",""],["🧲","magnet",""],["💣","bomb",""],["🔪","hocho","knife kitchen_knife"],["🗡️","dagger","dagger_knife"],["⚔️","crossed_swords",""],["🛡️","shield",""],["🔮","crystal_ball",""],["💈","barber","barber_pole"],["🔭","telescope",""],["🔬","microscope",""],["💊","pill",""],["💉","syringe",""],["🧬","dna",""],["🦠","microbe",""],["🧪","test_tube",""],["🌡️","thermometer",""],["🧹","broom",""],["🧻","roll_of_paper",""],["🚽","toilet",""],["🛁","bathtub",""],["🔑","key",""],["🗝️","old_key",""],["🚪","door",""],["🛋️","couch_and_lamp",""],["🛏️","bed",""],["🧸","teddy_bear",""],["🎁","gift","wrapped_gift"],["🎈","balloon",""],["🎉","tada","party_popper"],["🎊","confetti_ball",""],["✉️","envelope",""],["📩","envelope_with_arrow",""],["📦","package",""],["📝","memo","pencil"],["📌","pushpin",""],["📎","paperclip",""],["✂️","scissors",""],["📅","date","calendar"],["📈","chart_increasing","chart_with_upwards_trend"],["📉","chart_decreasing","chart_with_downwards_trend"],["📊","bar_chart",""],["🔒","lock","locked"],["🔓","unlock","unlocked"]]],["symbols",[["✅","white_check_mark","check_mark_button"],["☑️","check_box_with_check","ballot_box_with_check"],["✔️","check_mark","heavy_check_mark"],["❌","x","cross_mark"],["❎","cross_mark_button","negative_squared_cross_mark"],["➕","plus","heavy_plus_sign"],["➖","minus","heavy_minus_sign"],["➗","divide","heavy_division_sign"],["✖️","multiply","heavy_multiplication_x"],["❓","question","red_question_mark"],["❔","grey_question","white_question_mark"],["❗","exclamation","red_exclamation_mark heavy_exclamation_mark"],["❕","grey_exclamation","white_exclamation_mark"],["‼️","bangbang","double_exclamation_mark"],["⁉️","interrobang","exclamation_question_mark"],["💲","heavy_dollar_sign",""],["♻️","recycle","recycling_symbol"],["⚠️","warning",""],["🚫","prohibited","no_entry_sign"],["⛔","no_entry",""],["📛","name_badge",""],["🔞","underage","no_one_under_eighteen"],["🆗","ok","ok_button"],["🆕","new","new_button"],["🆒","cool","cool_button"],["🆓","free","free_button"],["🆙","up","up_button up!_button"],["🔝","top","top_arrow"],["🔜","soon","soon_arrow"],["🔛","on","on_arrow on!_arrow"],["🔚","end","end_arrow"],["🔙","back","back_arrow"],["▶️","play_button","arrow_forward"],["⏸️","pause_button","double_vertical_bar"],["⏹️","stop_button","black_square_for_stop"],["⏺️","record_button","black_circle_for_record"],["⏭️","next_track_button","black_right_pointing_double_triangle_with_vertical_bar"],["⏮️","last_track_button","previous_track_button black_left_pointing_double_triangle_with_vertical_bar"],["⏩","fast_forward","fast_forward_button fast-forward_button"],["⏪","rewind","fast_reverse_button"],["🔀","shuffle_tracks_button","twisted_rightwards_arrows"],["🔁","repeat","repeat_button"],["🔂","repeat_one","repeat_single_button"],["🔼","arrow_up_small","upwards_button"],["🔽","downwards_button","arrow_down_small"],["➡️","right_arrow","arrow_right"],["⬅️","left_arrow","arrow_left"],["⬆️","up_arrow","arrow_up"],["⬇️","arrow_down","down_arrow"],["↗️","up-right_arrow","up_right_arrow arrow_upper_right"],["↘️","down_right_arrow","down-right_arrow arrow_lower_right"],["↙️","down_left_arrow","down-left_arrow arrow_lower_left"],["↖️","up-left_arrow","up_left_arrow arrow_upper_left"],["↕️","arrow_up_down","up_down_arrow up-down_arrow"],["↔️","left-right_arrow","left_right_arrow"],["🔄","arrows_counterclockwise","counterclockwise_arrows_button"],["🔃","arrows_clockwise","clockwise_vertical_arrows"],["🎵","musical_note",""],["🎶","notes","musical_notes"],["〽️","part_alternation_mark",""],["©️","copyright",""],["®️","registered",""],["™️","tm","trade_mark"],["🔴","red_circle",""],["🟠","orange_circle",""],["🟡","yellow_circle",""],["🟢","green_circle",""],["🔵","blue_circle","large_blue_circle"],["🟣","purple_circle",""],["⚫","black_circle",""],["⚪","white_circle",""],["🟥","red_square",""],["🟩","green_square",""],["🟦","blue_square",""],["⬛","black_large_square",""],["⬜","white_large_square",""],["🔶","large_orange_diamond",""],["🔷","large_blue_diamond",""],["🏁","chequered_flag","checkered_flag"],["🚩","triangular_flag","triangular_flag_on_post"],["🏳️","white_flag","waving_white_flag"],["🏴","black_flag","waving_black_flag"]]]]

r.markdownToolbar.categoryNames = {
  smileys: r._('smileys'),
  people: r._('people'),
  hearts: r._('hearts'),
  nature: r._('nature'),
  food: r._('food'),
  activity: r._('activity'),
  objects: r._('objects'),
  symbols: r._('symbols')
}

$(function() {
  var mt = r.markdownToolbar

  function textareaFor(el) {
    return $(el).closest('.usertext-edit').find('textarea').first()[0]
  }

  function changed(ta) {
    // let warn-on-unload and anything else watching the box notice
    $(ta).trigger('keypress').trigger('input').trigger('change')
  }

  // wrap the selection (or a placeholder) in before/after and select it
  function surround(ta, before, after, placeholder) {
    var start = ta.selectionStart
    var end = ta.selectionEnd
    var value = ta.value
    var text = value.slice(start, end) || placeholder
    ta.value = value.slice(0, start) + before + text + after + value.slice(end)
    ta.focus()
    ta.setSelectionRange(start + before.length,
                         start + before.length + text.length)
    changed(ta)
  }

  // put prefix in front of every line the selection touches
  function prefixLines(ta, prefix, placeholder) {
    var value = ta.value
    var start = value.lastIndexOf('\n', ta.selectionStart - 1) + 1
    var end = ta.selectionEnd
    var text = value.slice(start, end) || placeholder
    var lines = text.split('\n').map(function(line) {
      return prefix + line
    }).join('\n')
    // block markup needs a blank line before it to start a new block
    var lead = (start > 0 && value.slice(start - 2, start) !== '\n\n') ? '\n' : ''
    ta.value = value.slice(0, start) + lead + lines + value.slice(end)
    ta.focus()
    ta.setSelectionRange(start + lead.length, start + lead.length + lines.length)
    changed(ta)
  }

  function insertText(ta, text) {
    var start = ta.selectionStart
    var value = ta.value
    ta.value = value.slice(0, start) + text + value.slice(ta.selectionEnd)
    ta.focus()
    ta.setSelectionRange(start + text.length, start + text.length)
    changed(ta)
  }

  var actions = {
    bold: function(ta) { surround(ta, '**', '**', r._('bold text')) },
    italic: function(ta) { surround(ta, '*', '*', r._('italic text')) },
    strike: function(ta) { surround(ta, '~~', '~~', r._('struck text')) },
    superscript: function(ta) { surround(ta, '^(', ')', r._('superscript')) },
    spoiler: function(ta) { surround(ta, '>!', '!<', r._('spoiler')) },
    code: function(ta) {
      var selected = ta.value.slice(ta.selectionStart, ta.selectionEnd)
      if (selected.indexOf('\n') !== -1) {
        prefixLines(ta, '    ', '')
      } else {
        surround(ta, '`', '`', r._('code'))
      }
    },
    quote: function(ta) { prefixLines(ta, '> ', r._('quoted text')) },
    list: function(ta) { prefixLines(ta, '* ', r._('item')) },
    link: function(ta) {
      var start = ta.selectionStart
      var text = ta.value.slice(start, ta.selectionEnd) || r._('link text')
      var url = 'https://'
      surround(ta, '[', '](' + url + ')', text)
      // select the url so it can be typed over
      var urlStart = start + 1 + text.length + 2
      ta.setSelectionRange(urlStart, urlStart + url.length)
    }
  }

  $(document).on('click', '.md-toolbar .md-tb[data-md]', function(e) {
    e.preventDefault()
    var ta = textareaFor(this)
    var action = actions[$(this).data('md')]
    if (ta && action) {
      action(ta)
    }
  })

  // Ctrl/Cmd+B and +I in the text box
  $(document).on('keydown', '.usertext-edit textarea', function(e) {
    if (!(e.ctrlKey || e.metaKey) || e.altKey || e.shiftKey) {
      return
    }
    var key = String.fromCharCode(e.which).toLowerCase()
    if (key === 'b' || key === 'i') {
      e.preventDefault()
      actions[key === 'b' ? 'bold' : 'italic'](this)
    }
  })

  /* emoji picker */

  function buildPicker() {
    var $picker = $('<div class="md-emoji-picker" role="dialog">')
    var $search = $('<input type="search" class="md-emoji-search">')
      .attr('placeholder', r._('search emoji'))
      .attr('aria-label', r._('search emoji'))
    var $list = $('<div class="md-emoji-list">')
    $picker.append($search, $list)

    $.each(mt.emoji, function(i, category) {
      var $section = $('<div class="md-emoji-category">')
      $section.append($('<div class="md-emoji-heading">')
        .text(mt.categoryNames[category[0]] || category[0]))
      var $grid = $('<div class="md-emoji-grid">')
      $.each(category[1], function(j, item) {
        $grid.append($('<button type="button" class="md-emoji">')
          .text(item[0])
          .attr('title', ':' + item[1] + ':')
          .attr('data-names', (item[1] + ' ' + item[2]).replace(/_/g, ' ')))
      })
      $list.append($section.append($grid))
    })
    return $picker
  }

  function closePickers() {
    $('.md-emoji-picker').remove()
    $('.md-picker-open').removeClass('md-picker-open')
    $('.md-tb-emoji').attr('aria-expanded', 'false')
  }

  $(document).on('click', '.md-toolbar .md-tb-emoji', function(e) {
    e.preventDefault()
    e.stopPropagation()
    var $toolbar = $(this).closest('.md-toolbar')
    var open = $toolbar.find('.md-emoji-picker').length
    closePickers()
    if (!open) {
      $toolbar.append(buildPicker())
      // the form clips overflow; let the picker show outside it
      $toolbar.closest('form, .usertext').addClass('md-picker-open')
      $(this).attr('aria-expanded', 'true')
      $toolbar.find('.md-emoji-search').focus()
    }
  })

  $(document).on('input', '.md-emoji-search', function() {
    var words = $.trim(this.value.toLowerCase().replace(/[:_]/g, ' '))
      .split(/\s+/).filter(Boolean)
    var $picker = $(this).closest('.md-emoji-picker')
    $picker.find('.md-emoji').each(function() {
      var names = this.getAttribute('data-names')
      var match = words.every(function(w) { return names.indexOf(w) !== -1 })
      this.style.display = match ? '' : 'none'
    })
    $picker.find('.md-emoji-category').each(function() {
      var any = $(this).find('.md-emoji').filter(function() {
        return this.style.display !== 'none'
      }).length
      this.style.display = any ? '' : 'none'
    })
  })

  $(document).on('click', '.md-emoji-picker .md-emoji', function(e) {
    e.preventDefault()
    e.stopPropagation()
    var ta = textareaFor(this)
    if (ta) {
      insertText(ta, $(this).text())
    }
    // keep the picker open when shift is held, to add several
    if (!e.shiftKey) {
      closePickers()
    }
  })

  $(document).on('click', '.md-emoji-picker', function(e) {
    e.stopPropagation()
  })

  $(document).on('click', closePickers)
  $(document).on('keydown', function(e) {
    if (e.which === 27) {
      closePickers()
    }
  })

  /* preview */

  $(document).on('click', '.md-toolbar .md-tb-preview', function(e) {
    e.preventDefault()
    var $button = $(this)
    var $edit = $button.closest('.usertext-edit')
    var $preview = $edit.find('.md-preview').first()
    var ta = textareaFor(this)

    if ($preview.is(':visible')) {
      $preview.hide().empty()
      $button.text(r._('preview')).attr('aria-pressed', 'false')
      return
    }

    $button.text(r._('hide preview')).attr('aria-pressed', 'true')
    $preview.show().text(r._('loading…'))
    $.ajax({
      type: 'POST',
      url: '/api/preview_markdown.json',
      data: {text: ta ? ta.value : '', uh: r.config.modhash},
      dataType: 'json'
    }).done(function(res) {
      if (res && res.error) {
        $preview.text(res.error)
      } else if (res && res.html) {
        // rendered and sanitized by the server, exactly as it would be
        // once saved. The API escapes HTML in JSON (like body_html), so
        // unescape it first.
        $preview.html($('<textarea>').html(res.html).text())
      } else {
        $preview.text(r._('nothing to preview'))
      }
    }).fail(function() {
      $preview.text(r._('preview failed'))
    })
  })

  // a fresh preview when the text changes would be stale; hide it
  $(document).on('input', '.usertext-edit textarea', function() {
    var $edit = $(this).closest('.usertext-edit')
    var $preview = $edit.find('.md-preview')
    if ($preview.is(':visible')) {
      $preview.hide().empty()
      $edit.find('.md-tb-preview').text(r._('preview'))
        .attr('aria-pressed', 'false')
    }
  })

  // spoilers reveal on hover; a tap or click reveals them on touch screens
  $(document).on('click', '.md .md-spoiler-text', function(e) {
    var $spoiler = $(this)
    if (!$spoiler.hasClass('revealed')) {
      // the first tap only reveals, so a link inside isn't followed yet
      e.preventDefault()
      $spoiler.addClass('revealed')
    }
  })
})
