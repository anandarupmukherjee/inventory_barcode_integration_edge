import 'bootstrap/dist/css/bootstrap.css';
import ButtonGroup from 'react-bootstrap/ButtonGroup'
import OverlayTrigger from 'react-bootstrap/OverlayTrigger'
import Tooltip from 'react-bootstrap/Tooltip'
import Button from 'react-bootstrap/Button'
import Spinner from 'react-bootstrap/Spinner'
import Card from 'react-bootstrap/Card'
import Col from 'react-bootstrap/Col'
import Row from 'react-bootstrap/Row'
import Container from 'react-bootstrap/Container'
import { MQTTProvider, useMQTTControl, useMQTTDispatch, useMQTTState } from './MQTTContext'
import React from 'react';
import APIBackend from './RestAPI'
import './app.css'
import 'bootstrap-icons/font/bootstrap-icons.css'
import { custom_new_message_action, CustomReducer } from './custom_mqtt';
import { Alert, Badge, Form, InputGroup } from 'react-bootstrap';


function App() {
  let [loaded, setLoaded] = React.useState(false)
  let [pending, setPending] = React.useState(false)
  let [error, setError] = React.useState(null)
  let [config, setConfig] = React.useState([])

  React.useEffect(() => {
    let do_load = async () => {
      setPending(true)
      try {
        let response = await APIBackend.api_get('http://' + document.location.host + '/config/config.json');
        if (response.status === 200) {
          const raw_conf = response.payload;
          console.log("config", raw_conf)
          setConfig(raw_conf)
          setLoaded(true)
        } else {
          console.log("ERROR LOADING CONFIG")
          setError("ERROR: Unable to load configuration!")
        }
      } catch (err) {
        console.err(err);
        setError("ERROR: Unable to load configuration!")
      }
    }
    if (!loaded && !pending) {
      do_load()
    }
  }, [loaded, pending])

  React.useEffect(() => {



  })

  if (!loaded) {
    return <Container fluid="md">
      <Card className='mt-2 text-center'>
        {error !== null ? <h1>{error}</h1> : <div><Spinner></Spinner> <h2 className='d-inline'>Loading Config</h2></div>}
      </Card>
    </Container>
  } else {
    return (
      <MQTTProvider
        host={config?.mqtt?.host ? config.mqtt.host : document.location.hostname}
        port={config?.mqtt?.port ?? 9001}
        prefix={config?.mqtt?.prefix ?? []}
        // subscriptions={["delivery_details/" + config.id, "status/" + config.id + "/alive"]}
        new_message_action={custom_new_message_action}
        reducer={CustomReducer}
        initial_state={{ product: "", expires: null, batch: "", quantity: "" }}
        debug={true}
      >
        <Dashboard config={config} />
      </MQTTProvider>
    )
  }


  

}

function Dashboard({ config = {} }) {

  let { connected } = useMQTTState()
  let variant = "danger"
  let text = "Disconnected"
  if (connected) {
    variant = "success"
    text = "Connected"
  }

  return (
    <Container fluid className="vh-100 p-0 d-flex flex-column">
      <Container fluid className="flex-grow-1 px-1 pt-2 px-sm-2">
        <Row className="m-0 mx-2 d-flex justify-content-center pt-2 pb-2">
          <Col>
            {/* <CurrentStatus /> */}
            <BatchForm config={config} />
          </Col>
        </Row>
      </Container>

      <div className='bottom_bar'>
        <ButtonGroup aria-label="Basic example">
          <OverlayTrigger
            placement='top'
            overlay={
              <Tooltip>
                Live updates over MQTT: {text}
              </Tooltip>
            }
          >
            <Button variant={variant} className='bi bi-rss'>{" " + text}</Button>
          </OverlayTrigger>
        </ButtonGroup>
      </div>
      
    </Container>
  )
}


function BatchForm({ config }) {

  const [boxCount, setBoxCount] = React.useState(1);
  let [suggestedSuppliers, setSuggestedSuppliers] = React.useState([])
  let [suggestedUsers, setSuggestedUsers] = React.useState([])
  let [suggestedProducts, setSuggestedProducts] = React.useState([])
  let [user, setUser] = React.useState("")
  let [loaded1, setLoaded1] = React.useState(false)
  let [loaded2, setLoaded2] = React.useState(false)
  let [pending1, setPending1] = React.useState(false)
  let [pending2, setPending2] = React.useState(false)

  let keysList = ["labelKey", "labelValue", "labelType"];
  let [palletInputsArray, setPalletInputsArray] = React.useState([])
  let [startTimeStamp, setStartTimeStamp] = React.useState(new Date().toISOString());

  let [labelValuesArray, setLabelValuesArray] = React.useState([]);
  let [inputTypesArray, setInputTypesArray] = React.useState(["text", "barcode", "QR", "QRAAS"]);
  let [printQty, setPrintQty] = React.useState(1);
  let [toggleClear, setToggleClear] = React.useState(false);


  const mogOptions = [];
  for(let i = 1; i <= 10; i++) {
    mogOptions.push(<option key={i} value={i}> {i}</option>);
  }
  

  const handleClick = () => {
    setBoxCount(boxCount + 1);
    updateLabelInputs(boxCount + 1);

  };
  const handleNegClick = () => {
    setBoxCount(boxCount - 1);
    updateLabelInputs(boxCount - 1);
  };

  function updatePalletInputs(newBoxCount) {
    let newPalletInputs = [...palletInputsArray];
  
    if (newBoxCount > boxCount) {
      newPalletInputs.push(undefined);
    }
  
    if (newBoxCount < boxCount) {
      newPalletInputs.pop();
    }
  
    setPalletInputsArray(newPalletInputs);

  }

  function updateLabelInputs(newBoxCount) {
    let newLabelValuesArray = [...labelValuesArray];
    if (newBoxCount > boxCount) {
      labelValuesArray.push(undefined);
    }
    if (newBoxCount < boxCount) {
      labelValuesArray.pop();
    }
    setLabelValuesArray(newLabelValuesArray);
  }



  function validateItemArray() {
    console.log("*** Validating Item Array ***");
    if (labelValuesArray.length === 0) {return false;}
    labelValuesArray.forEach((_, index) => {
      let itemKeys = Object.keys(labelValuesArray[index]);
      if (itemKeys.length !== keysList.length) {console.log("keys don't match"); return false;}
    });
    return true;
  }
  

  let { sendJsonMessage } = useMQTTControl()

  const onSubmit = () => {
    if (inputTypesArray && validateItemArray()) {
      // sendJsonMessage("delivery_details/" + config.id, 
      //                 { id: config.id,
      //                   items: palletInputsArray,
      //                   user: user,
      //                   startTimeStamp: startTimeStamp,
      //                 }, 1, true);

      sendJsonMessage("print/",
                      { id: config.id,
                        labelItems: labelValuesArray, 
                        qty: printQty
                      }, 1, true);

      alert("Successfully sent to printer!")
      if (toggleClear) {
        setBoxCount(1);
        setLabelValuesArray([]);
        console.log("*** Reset Form ***")
      }                
      
    
    } else {
      alert("Please fill out all fields")
    }
  }


  return <Card className='my-2'>
    <Card.Header><h4> Label Details: </h4></Card.Header>
    <Card.Body>


      <Form noValidate validated={true}>


        {[...Array(boxCount)].map((_, i) => (
          <InputGroup className="mb-3">
            <Form.Control
              placeholder= "Label Key"
              required
              value= {labelValuesArray[i] && labelValuesArray[i].labelKey ? labelValuesArray[i].labelKey : ''}
              onChange={e => {
                let newArray = [...labelValuesArray];
                newArray[i] = {...newArray[i], labelKey: e.target.value};
                setLabelValuesArray(newArray);
              }}
            />

            <Form.Control
              placeholder= "Label Value"
              required
              value= {labelValuesArray[i] && labelValuesArray[i].labelValue ? labelValuesArray[i].labelValue : ''}
              onChange={e => {
                let newArray = [...labelValuesArray];
                newArray[i] = {...newArray[i], labelValue: e.target.value};
                setLabelValuesArray(newArray);
              }}
            />



            <Form.Select 
              placeholder= "Type"
              value={labelValuesArray[i] && labelValuesArray[i].labelType ? labelValuesArray[i].labelType : ''}
              required
              onChange={e => {
                let newArray = [...labelValuesArray];
                newArray[i] = {...newArray[i], labelType: e.target.value};
                setLabelValuesArray(newArray);
              }}>
              <option value=""> Select Label Type </option>
              {inputTypesArray.map((i) => (
                <option>
                  {i}
                </option>
              ))}
            </Form.Select>


          
            <Button disabled={i+1<boxCount} variant="outline-secondary" onClick={handleClick}>+</Button>
            <Button disabled={i+1<boxCount || i==0} variant="outline-secondary" onClick={handleNegClick}>-</Button>
              
          </InputGroup>
        ))}



        

    
        {/* <Card.Subtitle className="mb-2 text-muted">Bins: {boxCount}, Gross Weight: {totalGrossWeight} kg, Net Weight: {totalNetWeight} kg </Card.Subtitle> */}



        <Row>
          <Col>
            <Form.Check // prettier-ignore
                type="checkbox"
                id={`toggleClear`}
                label={`Clear Form After Submit`}
                value = {toggleClear}
                onChange = {() => setToggleClear(!toggleClear)}
              />
          </Col>
          <Col>
            <Form.Control 
                placeholder= "Print Quantity"
                value={printQty}
                type="number"
                onChange={e => {
                  if (e.target.value > 0) {setPrintQty(e.target.value);}
                }}
                />
          </Col>
          <Col>
            <Button className='float-end' onClick={onSubmit}>Send to Printer</Button>
          </Col>
        </Row>         
      </Form>
    </Card.Body>
  </Card>
}

export default App;
