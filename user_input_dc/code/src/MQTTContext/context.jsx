import React from "react";
import Paho from 'paho-mqtt';
import uuid from 'uuid4';
import * as dayjs from 'dayjs';

import { default_new_message_action } from "./default_actions";
import { DefaultReducer } from "./default_reducer";

const MQTTSendContext = React.createContext();

export function useMQTTControl() {
  const context = React.useContext(MQTTSendContext);
  if (context === undefined) {
    throw new Error("useMQTTControl must be used within a MQTTProvider");
  }

  return context;
}

const MQTTStateContext = React.createContext();
const MQTTDispatchContext = React.createContext();

export function useMQTTState() {
  const context = React.useContext(MQTTStateContext);
  if (context === undefined) {
    throw new Error("useMQTTState must be used within a MQTTProvider");
  }

  return context;
}

export function useMQTTDispatch() {
  const context = React.useContext(MQTTDispatchContext);
  if (context === undefined) {
    throw new Error("useMQTTDispatch must be used within a MQTTProvider");
  }

  return context;
}

const SUB_STATE = { unsubscribed: 0, pending: 1, subscribed: 2 }

export const MQTTProvider = ({
  children,
  host,
  port = 1883,
  reducer = DefaultReducer,
  prefix = [],
  subscriptions = [],
  initial_state = {},
  new_message_action = default_new_message_action,
  debug = false
}) => {
  initial_state = { connected: false, ...initial_state }
  const clientID = uuid()
  const [connected, setConnected] = React.useState(false)
  const [connecting, setConnecting] = React.useState(false)
  const [state, dispatch] = React.useReducer(reducer, initial_state);
  const [message_queue, setMessageQueue] = React.useState([])
  const [send_queue, setSendQueue] = React.useState([])
  const [all_subbed, setAllSubbed] = React.useState(false)
  const [resub_ping, setReSubPing] = React.useState(false)
  const [sub_state, setSubState] = React.useState({})
  const [client, setClient] = React.useState(undefined)
  const [reset_substate, setResetSubstate] = React.useState(false)

  const subscribe = React.useCallback((topic) => {
    debug && console.log("Adding '" + topic + "' to subscription list")
    setSubState((prev) => ({ ...prev, [topic]: SUB_STATE.unsubscribed }))
    setAllSubbed(false)
  }, [debug])

  React.useEffect(() => {
    // called when a message arrives
    function onMessageArrived(message) {
      if (debug) { console.log("MQTT RCV: ", message.destinationName, message.payloadString); }
      setMessageQueue((old_queue) => ([...old_queue, { payload: JSON.parse(message.payloadString), topic: message.destinationName }]))
    }

    // called when the client loses its connection
    function onConnectionLost(responseObject) {
      if (responseObject.errorCode !== 0) {
        console.log("onConnectionLost:" + responseObject.errorMessage);
      } else {
        console.log("onConnectionLost: normal")
      }
      dispatch({ type: 'MQTT_STATUS', connected: false })
      setConnected(false)
      setResetSubstate(true)
    }

    if (!connected && !connecting) {
      let new_client = new Paho.Client(host, Number(port), clientID)
      console.log("Connecting to ", host, " on ", port)

      // called when the client connects
      function onConnect() {
        // Once a connection has been made, make a subscription and send a message.
        console.log("onConnect", clientID);
        dispatch({ type: 'MQTT_STATUS', connected: true })

        console.log("init subscribing to " + subscriptions)
        subscriptions.forEach(topic => {
          subscribe(topic);
        })

        setConnected(true)
        setConnecting(false)
      }

      // set callback handlers
      new_client.onConnectionLost = onConnectionLost;
      new_client.onMessageArrived = onMessageArrived;
      // connect the client
      new_client.connect({ onSuccess: onConnect, onFailure: onConnectionLost });
      setConnecting(true)
      setClient(new_client)
    }
  }, [connected, connecting, client, host, port, clientID, subscriptions, debug, sub_state, subscribe])

  React.useEffect(() => {
    if (reset_substate) {
      setResetSubstate(false)
      setAllSubbed(false)
      let new_substate = Object.keys(sub_state).reduce((acc, key) => { acc[key] = SUB_STATE.unsubscribed; return acc; }, {})
      // console.log("nss",new_substate,sub_state)
      setSubState(new_substate)
    }
  }, [reset_substate, sub_state])

  function sendJsonMessage(topic, payload, qos=0,retained=false) {
    //add timestamp to message if not present
    payload = { timestamp: dayjs().format(), ...payload }
    //ensure topic is wrapped in array
    if (!Array.isArray(topic))
      topic = [topic]
    //form strings
    const payload_string = JSON.stringify(payload)
    const topic_string = [...prefix, ...topic].join("/")
    if (debug) { console.log("MQTT SEND QUEUE: ", payload_string, " TO ", topic_string); }

    let message = new Paho.Message(payload_string);
    message.destinationName = topic_string;
    message.qos = qos;
    message.retained = retained;

    // client.send(message);
    setSendQueue((prev) => ([...prev,message]))
  }

  React.useEffect(() => {
    if (send_queue.length>0 && connected && client.isConnected()) {
      send_queue.forEach((message) => {
        if (debug) { console.log("MQTT SEND: ", message.payloadString, " TO ", message.topic); }
        client.send(message)
      })
      setSendQueue([])
    } 
  }, [client, connected, debug, send_queue])

  React.useEffect(() => {
    if (connected && client && client.isConnected() && !all_subbed) {
      let tmp_all_subbed = true
      for (let [topic, state] of Object.entries(sub_state)) {
        if (state === SUB_STATE.unsubscribed) {
          console.log("subscribing to " + topic)
          client.subscribe(topic, {
            onSuccess: () => {
              console.log("Successfully subscribed to '" + topic + "'")
              setSubState((prev) => ({ ...prev, [topic]: SUB_STATE.subscribed }))
            },
            onFailure: (_, code, msg) => {
              console.err(code, msg);
              setSubState((prev) => (
                { ...prev, [topic]: SUB_STATE.unsubscribed }))
            },
            timeout: 5
          });
          setSubState((prev) => ({ ...prev, [topic]: SUB_STATE.pending }))
          tmp_all_subbed = false
        }
        if (state === SUB_STATE.pending) {
          tmp_all_subbed = false
        }
      }
      setAllSubbed(tmp_all_subbed)
    } else if (!all_subbed && !resub_ping) {
      setReSubPing(true);
      setTimeout(() => (setReSubPing(false)), 1000);
    }
  }, [client, connected, sub_state, all_subbed, resub_ping])


  function unsubscribe(topic) {
    /*debug &&*/ console.log("Unsubscribing from '" + topic + "'")
    if (sub_state[topic]) {
      client.unsubscribe(topic)
      let new_substate = { ...sub_state }
      delete new_substate[topic]
      setSubState(new_substate)
    }
  }

  React.useEffect(() => {
    if (message_queue.length > 0) {
      for (let message of message_queue) {
        new_message_action(dispatch, message)
      }
      setMessageQueue([])
    }
  }, [message_queue, new_message_action]);

  return (
    <MQTTSendContext.Provider value={{ sendJsonMessage: sendJsonMessage, subscribe: subscribe, unsubscribe: unsubscribe }}>
      <MQTTStateContext.Provider value={state}>
        <MQTTDispatchContext.Provider value={dispatch}>
          {children}
        </MQTTDispatchContext.Provider>
      </MQTTStateContext.Provider>
    </MQTTSendContext.Provider>
  );
};
