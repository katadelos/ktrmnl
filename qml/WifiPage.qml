import QtQuick 2.15

Rectangle {
    id: root
    objectName: "wifiPage"
    property var theme
    property var translator
    property var controller
    property var wifiBackend
    property string page: "wifi"
    property int selectedIndex: 0
    property alias passwordText: passwordField.text
    property alias passwordRevealed: passwordField.revealed
    readonly property bool keyboardVisible: navigation.keyboardVisible
    property int previousNetworkCount: -1
    readonly property string activeLanguage: translator
        ? String(translator.language) : "en"
    readonly property int networkCount: wifiBackend ? wifiBackend.networks.length : 0
    readonly property int scanIndex: networkCount
    readonly property int backIndex: networkCount + 1
    readonly property int itemCount: backIndex + 1
    signal networkActivated(int index)
    signal selectionRequested(int index)
    signal backRequested()
    signal passwordSubmitted(string password)
    signal passwordEditRequested()

    color: theme.paper

    function translatedText(key) {
        var language = activeLanguage
        return translator.text(String(key))
    }

    function translatedFormat(key, values) {
        var language = activeLanguage
        return translator.format(String(key), values)
    }

    function pageTitle() {
        if (page === "wifi-password") return translatedText("wifi.password")
        if (page === "wifi-connect") return translatedText("wifi.connection")
        return translatedText("wifi.setup")
    }

    function insertText(text) {
        if (page === "wifi-password") keyboard.insert(String(text))
    }
    function deletePreviousCharacter() {
        if (page === "wifi-password") keyboard.erase()
    }
    function clearPassword() {
        passwordField.text = ""
        passwordField.conceal()
        focusPassword()
    }
    function focusPassword() {
        navigation.reset(false)
        Qt.callLater(function() {
            if (!root.visible || root.page !== "wifi-password") return
            passwordField.editor.cursorPosition = passwordField.text.length
            passwordField.editor.forceActiveFocus()
        })
    }
    function toggleKeyboard() {
        navigation.toggleKeyboard()
    }
    function dismissKeyboard() { navigation.focusActions() }
    function handleKeyboardAction(action) {
        return navigation.handleAction(action)
    }
    function activateConnectionAction() {
        if (!wifiBackend.passwordEditable || wifiBackend.connecting) return false
        passwordEditRequested()
        return true
    }
    function submitPassword() { root.passwordSubmitted(passwordField.text) }
    onPageChanged: if (page !== "wifi-password") passwordField.editor.focus = false
    onVisibleChanged: if (!visible) passwordField.editor.focus = false

    EditorNavigation {
        id: navigation
        theme: root.theme
        controller: root.controller
        field: passwordField
        keypad: keyboard
        onSubmitRequested: root.submitPassword()
        onCancelRequested: root.backRequested()
    }

    onNetworkCountChanged: {
        if (previousNetworkCount < 0) {
            previousNetworkCount = networkCount
            return
        }
        if (page === "wifi") {
            if (selectedIndex === previousNetworkCount)
                selectionRequested(scanIndex)
            else if (selectedIndex === previousNetworkCount + 1)
                selectionRequested(backIndex)
            else if (selectedIndex >= networkCount)
                selectionRequested(scanIndex)
        }
        previousNetworkCount = networkCount
    }

    Component.onCompleted: previousNetworkCount = networkCount

    PageHeader {
        id: header
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.leftMargin: root.theme.outerMargin
        anchors.rightMargin: root.theme.outerMargin
        theme: root.theme
        title: root.pageTitle()
        backVisible: true
        onBackRequested: root.backRequested()
    }

    Item {
        id: networkPicker
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: header.bottom
        anchors.bottom: parent.bottom
        visible: root.page === "wifi"

        Text {
            id: wifiStatus
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.top: parent.top
            anchors.leftMargin: root.theme.outerMargin
            anchors.rightMargin: root.theme.outerMargin
            height: Math.round(42 * root.theme.scale)
            text: root.wifiBackend.scanning
                ? root.translatedText("wifi.scan_active") : root.wifiBackend.statusText
            color: root.theme.ink
            font.family: root.theme.bodyFont
            font.pixelSize: root.theme.controlSize
            verticalAlignment: Text.AlignVCenter
            elide: Text.ElideRight
        }

        ListView {
            id: networkList
            objectName: "wifiNetworkList"
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.top: wifiStatus.bottom
            anchors.bottom: wifiFooter.top
            anchors.leftMargin: root.theme.outerMargin
            anchors.rightMargin: root.theme.outerMargin
            anchors.bottomMargin: root.theme.compactMargin
            clip: true
            interactive: true
            boundsBehavior: Flickable.StopAtBounds
            highlightFollowsCurrentItem: false
            highlightMoveDuration: 0
            highlightResizeDuration: 0
            model: root.networkCount
            currentIndex: root.theme.navigationFocus && root.selectedIndex < root.networkCount
                          ? root.selectedIndex : -1
            onCurrentIndexChanged: {
                if (currentIndex >= 0)
                    positionViewAtIndex(currentIndex, ListView.Contain)
            }

            delegate: Rectangle {
                id: networkRow
                width: networkList.width
                height: root.theme.rowHeight
                property var network: root.wifiBackend.networks[index]
                property bool selected: networkPress.highlighted
                    || (root.theme.navigationFocus && index === root.selectedIndex)
                property real signalLevel: Number(network.signal)
                property int signalBars: isNaN(signalLevel) ? 0
                                         : signalLevel >= -55 ? 4
                                         : signalLevel >= -67 ? 3
                                         : signalLevel >= -75 ? 2
                                         : 1
                property string rowTitle: network.ssid || "Hidden network"
                property string rowDetail: (network.security || "Open")
                    + (network.saved ? " · " + root.translatedText("detail.stored") : "")
                color: selected ? root.theme.selectedPaper : root.theme.paper

                Rectangle {
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.bottom: parent.bottom
                    height: 1
                    color: root.theme.ink
                }

                Column {
                    anchors.left: parent.left
                    anchors.right: signalIcon.left
                    anchors.leftMargin: root.theme.compactMargin
                    anchors.rightMargin: root.theme.compactMargin
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: 1

                    Text {
                        width: parent.width
                        text: networkRow.rowTitle
                        color: networkRow.selected ? root.theme.selectedInk : root.theme.ink
                        font.family: root.theme.displayFont
                        font.pixelSize: root.theme.bodySize
                        elide: Text.ElideRight
                    }

                    Text {
                        width: parent.width
                        text: networkRow.rowDetail
                        color: networkRow.selected ? root.theme.selectedInk : root.theme.ink
                        font.family: root.theme.bodyFont
                        font.pixelSize: root.theme.detailSize
                        elide: Text.ElideRight
                    }
                }

                Item {
                    id: signalIcon
                    anchors.right: arrow.left
                    anchors.rightMargin: Math.round(10 * root.theme.scale)
                    anchors.verticalCenter: parent.verticalCenter
                    width: Math.round(34 * root.theme.scale)
                    height: Math.round(24 * root.theme.scale)

                    Repeater {
                        model: 4

                        Rectangle {
                            readonly property int barHeight: Math.max(
                                                                 4,
                                                                 Math.round((5 + index * 4)
                                                                            * root.theme.scale))
                            x: index * Math.round(8 * root.theme.scale)
                            anchors.bottom: parent.bottom
                            width: Math.max(3, Math.round(5 * root.theme.scale))
                            height: barHeight
                            color: index < networkRow.signalBars
                                   ? (networkRow.selected ? root.theme.selectedInk : root.theme.ink)
                                   : (networkRow.selected ? root.theme.selectedPaper : root.theme.paper)
                            border.color: networkRow.selected ? root.theme.selectedInk : root.theme.ink
                            border.width: 1
                        }
                    }
                }

                Text {
                    id: arrow
                    anchors.right: parent.right
                    anchors.rightMargin: root.theme.compactMargin
                    anchors.verticalCenter: parent.verticalCenter
                    text: "›"
                    color: networkRow.selected ? root.theme.selectedInk : root.theme.ink
                    font.family: root.theme.displayFont
                    font.pixelSize: Math.round(root.theme.controlSize * 1.35)
                    font.bold: true
                }

                PressArea {
                    id: networkPress
                    anchors.fill: parent
                    theme: root.theme
                    actionData: String(networkRow.network.ssid)
                    onTriggered: function(ssid) {
                        for (var row = 0; row < root.networkCount; row++) {
                            if (String(root.wifiBackend.networks[row].ssid) === ssid) {
                                root.selectionRequested(row)
                                root.networkActivated(row)
                                break
                            }
                        }
                    }
                }
            }

        }

        Text {
            anchors.centerIn: networkList
            width: Math.min(networkList.width, Math.round(420 * root.theme.scale))
            visible: root.networkCount === 0 && !root.wifiBackend.scanning
            text: root.translatedText("wifi.no_networks")
            color: root.theme.ink
            font.family: root.theme.bodyFont
            font.pixelSize: root.theme.bodySize
            horizontalAlignment: Text.AlignHCenter
            lineHeight: 1.35
        }

        Row {
            id: wifiFooter
            objectName: "wifiFooterButtons"
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.bottom: parent.bottom
            anchors.leftMargin: root.theme.outerMargin
            anchors.rightMargin: root.theme.outerMargin
            anchors.bottomMargin: root.theme.compactMargin
            height: root.theme.rowHeight
            spacing: root.theme.compactMargin

            ActionButton {
                id: scanButton
                width: Math.floor((wifiFooter.width - wifiFooter.spacing) / 2)
                height: wifiFooter.height
                theme: root.theme
                text: root.wifiBackend.scanning
                    ? root.translatedText("wifi.scan_active")
                    : root.translatedText("action.scan_again")
                selected: root.selectedIndex === root.scanIndex
                onRequested: {
                    root.selectionRequested(root.scanIndex)
                    root.networkActivated(root.scanIndex)
                }
            }

            ActionButton {
                id: backButton
                width: wifiFooter.width - wifiFooter.spacing - scanButton.width
                height: wifiFooter.height
                theme: root.theme
                text: root.translatedText("action.back")
                selected: root.selectedIndex === root.backIndex
                onRequested: {
                    root.selectionRequested(root.backIndex)
                    root.networkActivated(root.backIndex)
                }
            }
        }
    }

    Item {
        id: passwordSurface
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: header.bottom
        anchors.bottom: parent.bottom
        visible: root.page === "wifi-password"

        Text {
            id: selectedNetwork
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.top: parent.top
            anchors.leftMargin: root.theme.outerMargin
            anchors.rightMargin: root.theme.outerMargin
            anchors.topMargin: Math.round(10 * root.theme.scale)
            text: root.wifiBackend.selectedSsid.length > 0
                  ? root.wifiBackend.selectedSsid + "  ·  " + root.wifiBackend.selectedSecurity
                  : root.translatedText("wifi.current_network")
            color: root.theme.ink
            font.family: root.theme.displayFont
            font.pixelSize: root.theme.bodySize
            font.bold: true
            elide: Text.ElideRight
        }

        TextEntry {
            id: passwordField
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.top: selectedNetwork.bottom
            anchors.leftMargin: root.theme.outerMargin
            anchors.rightMargin: root.theme.outerMargin
            anchors.topMargin: Math.round(9 * root.theme.scale)
            height: Math.round(64 * root.theme.scale)
            theme: root.theme
            translator: root.translator
            secret: true
            maximumLength: 64
            navigationSelected: navigation.focusZone === "field"
            revealSelected: navigation.focusZone === "reveal"
            placeholder: root.translatedText("keyboard.enter_password")
            onActivated: navigation.focusKeys()
            onTouched: navigation.touchField()
            onNavigationRequested: function(action) { navigation.handleAction(action) }
            onAccepted: root.submitPassword()
        }

        Keyboard {
            id: keyboard
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.bottom: parent.bottom
            height: Math.round(root.height * root.theme.keyboardHeightRatio)
            visible: root.keyboardVisible
            theme: root.theme
            translator: root.translator
            submitLabel: root.translatedText("action.connect")
            target: passwordField.editor
            onSubmitRequested: root.submitPassword()
        }

        Text {
            anchors.left: passwordField.left
            anchors.right: passwordField.right
            anchors.top: passwordField.bottom
            anchors.topMargin: root.theme.compactMargin
            visible: root.keyboardVisible && root.theme.navigationFocus
            text: root.translatedText(navigation.focusZone === "keys"
                ? "keyboard.navigation_hint" : "keyboard.cursor_hint")
            color: root.theme.ink
            font.family: root.theme.bodyFont
            font.pixelSize: root.theme.hintSize
            wrapMode: Text.Wrap
        }

        Column {
            anchors.centerIn: parent
            width: Math.min(parent.width - root.theme.outerMargin * 2,
                            Math.round(440 * root.theme.scale))
            spacing: root.theme.compactMargin
            visible: !root.keyboardVisible

            Text {
                width: parent.width
                text: root.translatedText("keyboard.closed")
                color: root.theme.ink
                font.family: root.theme.bodyFont
                font.pixelSize: root.theme.bodySize
                horizontalAlignment: Text.AlignHCenter
                wrapMode: Text.Wrap
            }

            ActionButtonRow {
                width: parent.width
                theme: root.theme
                leftText: root.translatedText("action.cancel")
                rightText: root.translatedText("action.connect")
                leftSelected: navigation.focusZone === "actions" && navigation.actionIndex === 0
                rightSelected: navigation.focusZone === "actions" && navigation.actionIndex === 1
                onLeftRequested: root.backRequested()
                onRightRequested: root.submitPassword()
            }
        }
    }

    Column {
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: header.bottom
        anchors.leftMargin: root.theme.outerMargin
        anchors.rightMargin: root.theme.outerMargin
        anchors.topMargin: root.theme.outerMargin
        spacing: Math.round(18 * root.theme.scale)
        visible: root.page === "wifi-connect"

        Text {
            width: parent.width
            text: root.wifiBackend.connecting
                ? root.translatedText("wifi.connecting")
                : (root.wifiBackend.connected
                   ? root.translatedText("wifi.connected")
                   : root.translatedText("wifi.connection_status"))
            color: root.theme.ink
            font.family: root.theme.displayFont
            font.pixelSize: root.theme.titleSize
            font.bold: true
        }

        Rectangle { width: parent.width; height: root.theme.divider; color: root.theme.ink }

        Text {
            width: parent.width
            text: root.wifiBackend.statusText
            color: root.theme.ink
            font.family: root.theme.bodyFont
            font.pixelSize: root.theme.bodySize
            wrapMode: Text.Wrap
        }

        ActionButton {
            objectName: "wifiChangePasswordButton"
            width: parent.width
            height: root.theme.rowHeight
            visible: root.wifiBackend.passwordEditable
            enabled: !root.wifiBackend.connecting
            theme: root.theme
            text: root.translatedText("wifi.change_password")
            selected: enabled
            onRequested: root.passwordEditRequested()
        }

    }

}
