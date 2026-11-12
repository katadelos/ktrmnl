import QtQuick 2.15

FocusScope {
    id: root
    objectName: "appView"
    focus: true

    property var controller
    property var contentModel
    property var wifiBackend
    property var inputBackend
    property var translator
    property color paperColor: "#ffffff"
    property color inkColor: "#000000"
    property real textScale: 1.0
    property real rowHeightScale: 1.0
    property real keyboardHeightRatio: 0.43
    property bool initialMenuOpen: false
    property string initialMenuPage: "root"

    enum Screen { Content, Menu, Editor, Language, FirstLanguage, Welcome, ModeGuide,
                  TrmnlId, WifiNetworks, WifiPassword, WifiConnection, Status }
    enum Overlay { NoOverlay, ClearConfig }
    enum Lifecycle { Constructing, Ready }
    property int screen: AppView.Content
    property int overlay: AppView.NoOverlay
    property int lifecycle: AppView.Constructing
    property string menuPage: "root"
    property int menuIndex: 0
    property var settingEditor: ({})
    property int languageIndex: 0
    property int appOverlayChoice: 0
    readonly property bool menuOpen: screen === AppView.Menu || screen === AppView.Editor
        || screen === AppView.Language || screen === AppView.WifiNetworks
        || screen === AppView.WifiPassword || screen === AppView.WifiConnection
        || screen === AppView.Status
    readonly property bool settingEditing: screen === AppView.Editor
    readonly property bool onboardingActive: screen === AppView.FirstLanguage
        || screen === AppView.Welcome || screen === AppView.ModeGuide
    readonly property bool languageSelectionActive: screen === AppView.FirstLanguage
        || screen === AppView.Language
    readonly property bool welcomeActive: screen === AppView.Welcome
    readonly property bool modeGuideActive: screen === AppView.ModeGuide
    readonly property bool trmnlIdVisible: screen === AppView.TrmnlId
    readonly property string appOverlay: overlay === AppView.ClearConfig ? "clear-config" : ""
    readonly property bool lowBatteryWarningActive: Boolean(
        controller && controller.lowBatteryWarningActive
    )
    readonly property bool uiModalActive: uiPolicy(screen, overlay) === "modal"
    readonly property bool entryKeyboardVisible: screen === AppView.WifiPassword
        ? wifiPage.keyboardVisible : (settingEditing && keyboardLayer.keyboardVisible)
    readonly property int displayRotation: controller.rotation
    readonly property int menuRowHeight: theme.rowHeight
    readonly property string activeLanguage: translator ? String(translator.language) : "en"

    function uiPolicy(nextScreen, nextOverlay) {
        if (nextOverlay !== AppView.NoOverlay || nextScreen === AppView.FirstLanguage
                || nextScreen === AppView.Welcome || nextScreen === AppView.ModeGuide
                || nextScreen === AppView.Language || nextScreen === AppView.TrmnlId)
            return "modal"
        return nextScreen === AppView.Content ? "content" : "menu"
    }

    function syncUiState() {
        if (!controller || lifecycle !== AppView.Ready) return
        // Read the state directly: derived bindings can update after this handler.
        controller.setUiState(uiPolicy(screen, overlay))
        if (screen === AppView.Content && overlay === AppView.NoOverlay)
            Qt.callLater(controller.requestFullRefresh)
        else
            Qt.callLater(controller.requestTransitionRefresh)
    }
    onScreenChanged: syncUiState()
    onOverlayChanged: syncUiState()

    function showScreen(next) {
        overlay = AppView.NoOverlay
        screen = next
        forceActiveFocus()
    }

    Theme {
        id: theme
        viewportWidth: root.width
        viewportHeight: root.height
        textScale: root.textScale
        rowHeightScale: root.rowHeightScale
        keyboardHeightRatio: root.keyboardHeightRatio
        language: root.translator.language
        touchAvailable: root.controller.touchAvailable
        paper: root.paperColor
        ink: root.inkColor
    }

    function translatedText(key, fallback) {
        var language = activeLanguage
        return translator.text(String(key), String(fallback || ""))
    }

    function translatedFormat(key, values) {
        var language = activeLanguage
        return translator.format(String(key), values)
    }

    function titleForPage(page) {
        if (page === "start") return translatedText("page.select_mode")
        if (page === "root") return "ktrmnl"
        if (page === "content") return translatedText("page.content")
        if (page === "display") return translatedText("page.display")
        if (page === "wifi-settings") return translatedText("page.network")
        if (page === "system") return translatedText("page.system")
        return "ktrmnl"
    }

    function modeLabel(mode) {
        if (mode === "trmnl") return translatedText("mode.trmnl")
        if (mode === "interrupt") return translatedText("mode.interrupt")
        if (mode === "local_images") return translatedText("mode.local_images")
        if (mode === "http_push") return translatedText("mode.http_push")
        return mode
    }

    function syncLanguageIndex() {
        for (var index = 0; index < translator.languages.length; index++) {
            if (String(translator.languages[index].code) === String(translator.language)) {
                languageIndex = index
                return
            }
        }
        languageIndex = 0
    }

    function openLanguageMenu() {
        syncLanguageIndex()
        openMenu("language")
    }

    function chooseLanguage(language) {
        var choosingForOnboarding = onboardingActive
        if (!translator.setLanguage(String(language), !choosingForOnboarding)) return
        syncLanguageIndex()
        if (choosingForOnboarding) {
            showScreen(AppView.Welcome)
        } else {
            openMenu("system")
        }
    }

    function handleLanguageAction(action) {
        var count = translator.languages.length
        if (count <= 0) return true
        var column = Math.floor(languageIndex / 4)
        var row = languageIndex % 4
        if (action === "left") {
            languageIndex = ((column + 2) % 3) * 4 + row
        } else if (action === "right") {
            languageIndex = ((column + 1) % 3) * 4 + row
        } else if (action === "up") {
            languageIndex = column * 4 + (row + 3) % 4
        } else if (action === "down") {
            languageIndex = column * 4 + (row + 1) % 4
        } else if (action === "select") {
            chooseLanguage(String(translator.languages[languageIndex].code))
        } else if ((action === "back" || action === "menu") && !onboardingActive) {
            openMenu("system")
        }
        return true
    }

    function showFirstRunPreview() {
        syncLanguageIndex()
        showScreen(AppView.FirstLanguage)
    }

    function finishFirstRunPreview() { showScreen(AppView.Content) }

    function beginFirstRunSetup() { showScreen(AppView.ModeGuide) }

    function finishFirstRunSetup() {
        if (controller.finishFirstTimeSetup()) openMenu("content")
    }

    function showClearConfigConfirmation() {
        appOverlayChoice = 0
        overlay = AppView.ClearConfig
    }

    function showTrmnlId() {
        if (!controller || String(controller.friendlyId || "").length === 0)
            return
        showScreen(AppView.TrmnlId)
    }

    function closeTrmnlId() {
        openMenu("system")
    }

    function resolveAppOverlay(index) {
        if (index === 0) overlay = AppView.NoOverlay
        else if (controller.clearConfig()) showFirstRunPreview()
    }

    function handleAppOverlayAction(action) {
        if (appOverlay.length === 0) return false
        if (action === "left" || action === "up") appOverlayChoice = 0
        else if (action === "right" || action === "down") appOverlayChoice = 1
        else if (action === "select") resolveAppOverlay(appOverlayChoice)
        else if (action === "back" || action === "menu") resolveAppOverlay(0)
        return true
    }

    function appOverlayTitle() {
        return translatedText("config.clear_confirm_title")
    }

    function appOverlayMessage() {
        return translatedText("config.clear_confirm_message")
    }

    function appOverlayConfirmLabel() {
        return translatedText("action.reset")
    }

    function openMenu(page) {
        menuPage = page
        menuIndex = 0
        controller.openMenuPage(page)
        var screens = { "language": AppView.Language, "wifi": AppView.WifiNetworks,
                        "wifi-password": AppView.WifiPassword,
                        "wifi-connect": AppView.WifiConnection, "status": AppView.Status }
        showScreen(screens[page] === undefined ? AppView.Menu : screens[page])
        if (page === "wifi") wifiBackend.scan()
        forceActiveFocus()
        if (page === "wifi-password")
            Qt.callLater(function() { wifiPage.focusPassword() })
    }

    function closeMenu() { showScreen(AppView.Content) }
    function closeEditor() { showScreen(AppView.Menu) }

    function chooseMode(mode) {
        controller.setMode(mode)
        closeMenu()
    }

    function openSetting(itemId) {
        for (var row = 0; row < controller.menuItems.length; row++) {
            if (String(controller.menuItems[row].id) === String(itemId)) {
                menuIndex = row
                break
            }
        }
        var definition = controller.settingDefinition(itemId)
        if (!definition || !definition.kind) return
        if (definition.kind === "toggle") {
            controller.toggleSetting(itemId)
            return
        }
        if (definition.kind === "choice") {
            cycleChoice(itemId, 1)
        } else {
            settingEditor = definition
            showScreen(AppView.Editor)
            keyboardLayer.begin(definition)
        }
    }

    function applyChoice(itemId, value) {
        controller.applySetting(String(itemId), value)
    }

    function saveSetting(value) {
        if (controller.applySetting(String(settingEditor.itemId), value))
            closeEditor()
    }

    function cycleChoice(itemId, direction) {
        var definition = controller.settingDefinition(itemId)
        if (!definition || !definition.choices || definition.choices.length === 0) return
        var selected = 0
        for (var index = 0; index < definition.choices.length; index++) {
            if (definition.choices[index].selected) {
                selected = index
                break
            }
        }
        var next = (selected + direction + definition.choices.length) % definition.choices.length
        applyChoice(itemId, definition.choices[next].value)
    }

    function selectWifiIndex(index) {
        var networkCount = wifiBackend.networks.length
        if (index < networkCount) {
            var network = wifiBackend.networks[index]
            wifiBackend.selectNetwork(network.ssid)
            if (wifiBackend.requiresPassword) {
                wifiPage.clearPassword()
                openMenu("wifi-password")
            } else {
                wifiBackend.connectNetwork(network.ssid, "")
                openMenu("wifi-connect")
            }
        } else if (index === networkCount) {
            wifiBackend.scan()
        } else {
            openMenu("wifi-settings")
        }
    }

    function submitPassword(password) {
        if (!wifiBackend.selectedSsid || !password.length) return
        wifiBackend.connectNetwork(wifiBackend.selectedSsid, password)
        openMenu("wifi-connect")
    }

    function activate(itemId) {
        if (itemId === "mode-trmnl") chooseMode("trmnl")
        else if (itemId === "mode-interrupt") chooseMode("interrupt")
        else if (itemId === "mode-local") chooseMode("local_images")
        else if (itemId === "mode-push") chooseMode("http_push")
        else if (itemId === "change-mode") openMenu("start")
        else if (itemId === "content-settings") openMenu("content")
        else if (itemId === "display-settings") openMenu("display")
        else if (itemId === "wifi-settings") openMenu("wifi-settings")
        else if (itemId === "system-settings") openMenu("system")
        else if (itemId === "status") {
            controller.refreshDeviceStatus()
            openMenu("status")
        } else if (itemId === "wifi-setup") openMenu("wifi")
        else if (itemId === "language") openLanguageMenu()
        else if (itemId === "show-trmnl-id") showTrmnlId()
        else if (itemId === "clear-config") showClearConfigConfirmation()
        else if (itemId === "exit") controller.requestExit()
        else if (itemId.indexOf("setting-") === 0) openSetting(itemId)
        else if (itemId === "back") {
            if (menuPage === "start") controller.requestExit()
            else if (menuPage === "root") closeMenu()
            else if (menuPage === "wifi-password" || menuPage === "wifi-connect") openMenu("wifi")
            else if (menuPage === "wifi") openMenu("wifi-settings")
            else if (menuPage === "language") openMenu("system")
            else openMenu("root")
        }
    }

    function menuItemSelectable(index) {
        return index >= 0 && index < controller.menuItems.length
            && String(controller.menuItems[index].kind || "") !== "info"
    }

    function moveMenuSelection(direction) {
        var count = controller.menuItems.length
        if (count <= 0) return
        for (var offset = 1; offset <= count; offset++) {
            var candidate = (menuIndex + direction * offset + count * offset) % count
            if (menuItemSelectable(candidate)) {
                menuIndex = candidate
                return
            }
        }
    }

    // Raw reader buttons are described in physical axes. Qt keyboard events
    // already describe the logical viewport and therefore bypass this mapping.
    function orientedAction(action) {
        var rotation = ((-displayRotation % 360) + 360) % 360
        if (action !== "up" && action !== "down" && action !== "left" && action !== "right") return action
        if (rotation === 90) {
            if (action === "up") return "right"
            if (action === "right") return "down"
            if (action === "down") return "left"
            return "up"
        }
        if (rotation === 180) {
            if (action === "up") return "down"
            if (action === "right") return "left"
            if (action === "down") return "up"
            return "right"
        }
        if (rotation === 270) {
            if (action === "up") return "left"
            if (action === "right") return "up"
            if (action === "down") return "right"
            return "down"
        }
        return action
    }

    function handleAction(action, physicalAxes) {
        if (action === "up" || action === "down" || action === "left"
                || action === "right" || action === "select" || action === "menu"
                || action === "back" || action === "home" || action === "keyboard")
            theme.inputMode = Theme.Navigation

        if (lowBatteryWarningActive) {
            controller.dismissLowBatteryWarning()
            return
        }

        if (physicalAxes) action = orientedAction(action)

        if (modeGuideActive) {
            if (action === "select" || action === "right")
                finishFirstRunSetup()
            return
        }
        if (trmnlIdVisible) {
            if (action === "select" || action === "right" || action === "back"
                    || action === "left" || action === "menu")
                closeTrmnlId()
            return
        }
        if (appOverlay.length > 0) {
            handleAppOverlayAction(action)
            return
        }
        if (languageSelectionActive) {
            handleLanguageAction(action)
            return
        }
        if (welcomeActive) {
            if (action === "select" || action === "right")
                beginFirstRunSetup()
            else if (action === "back" || action === "left" || action === "menu") {
                showFirstRunPreview()
            }
            return
        }
        if (controller.handleInput(action)) return

        if (!menuOpen) {
            if (contentView.handleAction(action)) return
            if (action === "menu" || action === "select" || action === "home") openMenu("root")
            else if (action === "next") contentModel.refresh()
            return
        }

        if (settingEditing) {
            if (action === "keyboard") keyboardLayer.toggleKeyboard()
            else if (action === "back" || action === "menu") closeEditor()
            else if (action === "backspace") keyboardLayer.deletePreviousCharacter()
            else if (action === "up" || action === "down" || action === "left"
                     || action === "right" || action === "select") {
                var settingHandled = keyboardLayer.handleKeyboardAction(action)
                if (!settingHandled && !keyboardLayer.keyboardVisible
                        && (action === "select" || action === "right"))
                    keyboardLayer.saveValue()
                else if (!settingHandled && !keyboardLayer.keyboardVisible
                         && action === "left")
                    closeEditor()
            }
            return
        }

        if (menuPage === "wifi") {
            if (action === "up") {
                if (menuIndex >= wifiPage.scanIndex) {
                    if (wifiPage.networkCount > 0)
                        menuIndex = wifiPage.networkCount - 1
                } else {
                    menuIndex = Math.max(0, menuIndex - 1)
                }
            } else if (action === "down") {
                if (menuIndex < wifiPage.networkCount - 1)
                    menuIndex += 1
                else if (menuIndex < wifiPage.networkCount)
                    menuIndex = wifiPage.scanIndex
            } else if (action === "left") {
                if (menuIndex === wifiPage.backIndex)
                    menuIndex = wifiPage.scanIndex
                else if (menuIndex < wifiPage.scanIndex)
                    openMenu("wifi-settings")
            } else if (action === "right") {
                if (menuIndex === wifiPage.scanIndex)
                    menuIndex = wifiPage.backIndex
                else if (menuIndex < wifiPage.scanIndex)
                    selectWifiIndex(menuIndex)
            } else if (action === "select") {
                selectWifiIndex(menuIndex)
            } else if (action === "back" || action === "menu") {
                openMenu("wifi-settings")
            }
            return
        }

        if (menuPage === "wifi-password") {
            if (action === "keyboard") wifiPage.toggleKeyboard()
            else if (action === "back" || action === "menu") openMenu("wifi")
            else if (action === "backspace") wifiPage.deletePreviousCharacter()
            else if (action === "up" || action === "down" || action === "left"
                     || action === "right" || action === "select") {
                var wifiHandled = wifiPage.handleKeyboardAction(action)
                if (!wifiHandled && !wifiPage.keyboardVisible
                        && (action === "select" || action === "right"))
                    wifiPage.submitPassword()
                else if (!wifiHandled && !wifiPage.keyboardVisible && action === "left")
                    openMenu("wifi")
            }
            return
        }

        if (menuPage === "wifi-connect") {
            if (action === "select" || action === "right") {
                if (!wifiPage.activateConnectionAction()) openMenu("wifi")
            } else if (action === "back" || action === "left" || action === "menu") openMenu("wifi")
            return
        }

        if (menuPage === "status") {
            if (action === "up" || action === "down") statusPage.scroll(action === "up" ? -1 : 1)
            else if (action === "select" || action === "right" || action === "back" || action === "left" || action === "menu") openMenu("wifi-settings")
            return
        }

        var menuItemCount = controller.menuItems.length
        if (action === "up" && menuItemCount > 0)
            moveMenuSelection(-1)
        else if (action === "down" && menuItemCount > 0)
            moveMenuSelection(1)
        else if (action === "select" || action === "right") {
            if (menuItemSelectable(menuIndex)) {
                var selectedItem = controller.menuItems[menuIndex]
                if (String(selectedItem.kind || "") === "choice")
                    cycleChoice(String(selectedItem.id), 1)
                else
                    activate(String(selectedItem.id))
            }
        } else if (action === "left") {
            if (menuIndex >= 0 && menuIndex < controller.menuItems.length
                    && String(controller.menuItems[menuIndex].kind || "") === "choice")
                cycleChoice(String(controller.menuItems[menuIndex].id), -1)
            else
                activate("back")
        } else if (action === "back" || action === "menu") activate("back")
        else if (action === "home") closeMenu()
    }

    Component.onCompleted: {
        syncLanguageIndex()
        if (controller.firstRun) showFirstRunPreview()
        else if (initialMenuOpen) openMenu(initialMenuPage)
        lifecycle = AppView.Ready
        syncUiState()
        forceActiveFocus()
    }

    Keys.onPressed: function(event) {
        if (event.key === Qt.Key_Up) root.handleAction("up", false)
        else if (event.key === Qt.Key_Down) root.handleAction("down", false)
        else if (event.key === Qt.Key_Left) root.handleAction("left", false)
        else if (event.key === Qt.Key_Right) root.handleAction("right", false)
        else if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter) root.handleAction("select", false)
        else if (event.key === Qt.Key_Space && root.menuOpen && root.menuPage === "wifi-password") wifiPage.insertText(" ")
        else if (event.key === Qt.Key_Space && root.settingEditing) keyboardLayer.insertText(" ")
        else if (event.key === Qt.Key_Space) root.handleAction("select", false)
        else if (event.key === Qt.Key_Escape) root.handleAction("back", false)
        else if (event.key === Qt.Key_Backspace && root.menuOpen && root.menuPage === "wifi-password") wifiPage.deletePreviousCharacter()
        else if (event.key === Qt.Key_Backspace && root.settingEditing) keyboardLayer.deletePreviousCharacter()
        else if (event.key === Qt.Key_Backspace) root.handleAction("back", false)
        else if (root.menuOpen && root.menuPage === "wifi-password"
                 && event.text.length > 0
                 && event.text.charCodeAt(0) >= 32
                 && !(event.modifiers & Qt.ControlModifier)
                 && !(event.modifiers & Qt.MetaModifier))
            wifiPage.insertText(event.text)
        else if (root.settingEditing
                 && event.text.length > 0
                 && event.text.charCodeAt(0) >= 32
                 && !(event.modifiers & Qt.ControlModifier)
                 && !(event.modifiers & Qt.MetaModifier))
            keyboardLayer.insertText(event.text)
        else if (event.key === Qt.Key_M) root.handleAction("menu", false)
        else if (event.key === Qt.Key_R) root.handleAction("next", false)
        else if (event.key === Qt.Key_Home) root.handleAction("home", false)
        else return
        event.accepted = true
    }

    Connections {
        target: root.inputBackend
        function onActionReceived(action) { root.handleAction(action, true) }
        function onTextReceived(text) {
            if (root.menuOpen && root.menuPage === "wifi-password")
                wifiPage.insertText(text)
            else if (root.settingEditing)
                keyboardLayer.insertText(text)
        }
    }

    Connections {
        target: root.controller
        function onMenuItemsChanged() {
            var lastIndex = root.controller.menuItems.length - 1
            root.menuIndex = Math.max(0, Math.min(root.menuIndex, lastIndex))
            if (!root.menuItemSelectable(root.menuIndex))
                root.moveMenuSelection(1)
        }

        function onBatteryAlertChanged() {
            if (root.lifecycle === AppView.Ready)
                Qt.callLater(root.controller.requestTransitionRefresh)
        }
        function onConfigStateChanged() {
            if (root.controller.firstRun && !root.onboardingActive) root.showFirstRunPreview()
            else if (root.trmnlIdVisible && !root.controller.friendlyId.length)
                root.openMenu("system")
        }
    }

    LanguageSelection {
        anchors.fill: parent
        visible: root.languageSelectionActive
        z: 45
        theme: theme
        translator: root.translator
        onboarding: root.onboardingActive
        selectedIndex: root.languageIndex
        onSelectionRequested: function(index) { root.languageIndex = index }
        onLanguageRequested: function(language) { root.chooseLanguage(language) }
        onBackRequested: {
            if (!root.onboardingActive) root.openMenu("system")
        }
    }

    FirstRunWelcome {
        anchors.fill: parent
        visible: root.welcomeActive
        z: 45
        theme: theme
        translator: root.translator
        onBeginRequested: root.beginFirstRunSetup()
    }

    ModeGuidePage {
        anchors.fill: parent
        visible: root.modeGuideActive
        z: 45
        theme: theme
        translator: root.translator
        onFinishRequested: root.finishFirstRunSetup()
    }

    TrmnlIdPage {
        anchors.fill: parent
        visible: root.trmnlIdVisible
        z: 45
        theme: theme
        translator: root.translator
        friendlyId: root.controller ? String(root.controller.friendlyId || "") : ""
        deviceName: root.controller ? String(root.controller.deviceName || "") : ""
        onBackRequested: root.closeTrmnlId()
    }

    ContentView {
        id: contentView
        anchors.fill: parent
        visible: root.screen === AppView.Content
        theme: theme
        translator: root.translator
        imageSource: root.contentModel.imageSource
        imageRevision: root.contentModel.imageRevision
        imagePresentation: root.contentModel.imagePresentation
        hasContent: root.contentModel.hasContent
        busy: root.contentModel.busy
        presentationState: root.contentModel.presentationState
        statusText: root.contentModel.status
        contentMode: root.contentModel.mode
        wifiConnected: Boolean(root.wifiBackend && root.wifiBackend.connected)
        onMenuRequested: {
            theme.inputMode = Theme.Touch
            root.openMenu("root")
        }
        onContentSettingsRequested: root.openMenu("content")
        onImageFolderRequested: {
            root.openMenu("content")
            root.openSetting("setting-local-directory")
        }
        onWifiSettingsRequested: root.openMenu("wifi")
        onRetryRequested: root.contentModel.refresh()
    }

    MenuPage {
        anchors.fill: parent
        visible: root.menuOpen
                 && (root.menuPage === "start" || root.menuPage === "root"
                     || root.menuPage === "content" || root.menuPage === "display"
                     || root.menuPage === "wifi-settings" || root.menuPage === "system")
        theme: theme
        translator: root.translator
        title: root.titleForPage(root.menuPage)
        hint: root.menuPage === "display" && root.controller.qtBackendAvailable
              ? root.translatedText("backend.next_launch",
                                    "Qt backend changes take effect when you reopen the app.")
              : ""
        items: root.controller.menuItems
        selectedIndex: root.menuIndex
        onSelectionRequested: function(index) { root.menuIndex = index }
        onActivated: function(itemId) { root.activate(itemId) }
        onChoiceRequested: function(itemId, value) { root.applyChoice(itemId, value) }
        onBackRequested: root.activate("back")
    }

    KeyboardLayer {
        id: keyboardLayer
        anchors.fill: parent
        visible: root.settingEditing
        z: 40
        theme: theme
        translator: root.translator
        controller: root.controller
        errorText: root.controller.settingError
        onSaveRequested: function(value) { root.saveSetting(value) }
        onCancelRequested: root.closeEditor()
    }

    StatusPage {
        id: statusPage
        anchors.fill: parent
        visible: root.menuOpen && root.menuPage === "status"
        theme: theme
        translator: root.translator
        rows: [
            {"label": root.translatedText("status.ssid"), "value": root.controller.wifiNetworkText},
            {"label": root.translatedText("status.signal_strength"), "value": root.controller.wifiSignalText},
            {"label": root.translatedText("status.device"), "value": root.controller.model},
            {"label": root.translatedText("status.battery"), "value": root.controller.batteryText},
            {"label": root.translatedText("sleep.title"), "value": root.controller.powerStatus}
        ]
        onBackRequested: root.openMenu("wifi-settings")
    }

    WifiPage {
        id: wifiPage
        anchors.fill: parent
        visible: root.menuOpen && (root.menuPage === "wifi" || root.menuPage === "wifi-password" || root.menuPage === "wifi-connect")
        theme: theme
        translator: root.translator
        controller: root.controller
        wifiBackend: root.wifiBackend
        page: root.menuPage
        selectedIndex: root.menuIndex
        onSelectionRequested: function(index) { root.menuIndex = index }
        onNetworkActivated: function(index) { root.selectWifiIndex(index) }
        onBackRequested: {
            if (root.menuPage === "wifi-password" || root.menuPage === "wifi-connect") root.openMenu("wifi")
            else root.openMenu("wifi-settings")
        }
        onPasswordSubmitted: function(password) { root.submitPassword(password) }
        onPasswordEditRequested: {
            wifiPage.clearPassword()
            root.openMenu("wifi-password")
        }
    }

    InterruptOverlay {
        anchors.fill: parent
        visible: root.contentModel.interruptActive && !root.menuOpen
                 && !root.uiModalActive
        z: 50
        theme: theme
        translator: root.translator
        title: root.contentModel.interruptTitle
        message: root.contentModel.interruptMessage
        inverted: root.contentModel.interruptInverted
        onDismissRequested: root.controller.dismissInterrupt()
    }

    InterruptOverlay {
        objectName: "lowBatteryOverlay"
        anchors.fill: parent
        visible: root.lowBatteryWarningActive

        z: 70
        theme: theme
        translator: root.translator
        title: root.translatedText("battery.low_title")
        message: root.translatedText("battery.low_message").replace(
            "%1", String(root.controller.batteryPercent)
        )
        opaqueBackdrop: true
        dismissLabel: root.translatedText("action.done")
        onDismissRequested: root.controller.dismissLowBatteryWarning()
    }

    InterruptOverlay {
        objectName: "appInterruptOverlay"
        anchors.fill: parent
        visible: root.appOverlay.length > 0
        z: 60
        theme: theme
        translator: root.translator
        title: root.appOverlayTitle()
        message: root.appOverlayMessage()
        opaqueBackdrop: true
        choices: [root.translatedText("action.cancel"), root.appOverlayConfirmLabel()]
        selectedIndex: root.appOverlayChoice
        onChoiceRequested: function(index) { root.resolveAppOverlay(index) }
    }

}
