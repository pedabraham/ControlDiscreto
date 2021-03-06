import control
import numpy as np
import matplotlib.pyplot as plt
from scipy.signal import lti, step2
from flask import Flask, render_template, request, Response
import io
import json

# Función necesaria en el diseño de controlador mediante LGR
# Se obtiene con los paramentros de comportamiento deseado
def poloDominante(Mp1, ta):
    Mp = Mp1 / 100
    L = np.log(Mp)**2
    E = np.sqrt(L / (np.pi**2 + L))
    Wn = 4 / (E * ta)
    polosDominantes = np.roots([1, 2 * E * Wn, Wn**2])
    print(ta)
    print('poloDominante: ' + str(polosDominantes[0]))
    return polosDominantes[0]


def mod(n):
    return np.sqrt(np.real(n)**2 + np.imag(n)**2)

# Diseño de controlador mediante el metodo de lugar geometrico de las raices
# Se necesita saber,"G" la funcion de trasferencia de la planta, la accion de control,
# y el polo dominante
# La función regresa los datos para ver graficamente la respuesta al impluso y el LGR
# ademas de los valores de las constantes necesarias para controlar la planta
def controladorByLGR(G, accion, PoloD):
    Tin, yin = control.step_response(G / (G + 1))
    rlistI, klistI = control.root_locus(G, Plot=False)
    # se define que tipo de controlador se debe de usar en este caso se usara el PD por lo que a nuestra funcion original no se le agrega nada conocido.
    PD = control.TransferFunction([1], [1])
    PI = control.TransferFunction([1], [1, 0])
    PID = control.TransferFunction([1, 2], [1, 0])
    if accion == "PD":
        G = G * PD
    elif accion == "PI" or accion == "I":
        G = G * PI
    elif accion == "PID":
        G = G * PID
    G = G.minreal()
    tfgf = control.TransferFunction([1], [1])  # transfer function gain finder
    for zero in G.zero():
        tfp = control.TransferFunction(
            [1], [1, -1 * zero])  # transfer funtion of prube
        tfgf = tfgf * tfp
    tfg = G * tfgf
    gain = tfg.num[0][0][0]
    # Posteriomente se hace la suma de los angulos de polos hacia el polo dominante.
    angulosPolo = 0
    for polo in G.pole():
        if np.real(polo) > np.real(PoloD):
            angulosPolo += np.pi - \
                np.arctan(np.imag(PoloD) /
                          np.abs(np.real(polo) - np.real(PoloD)))
        else:
            angulosPolo += np.arctan(np.imag(PoloD) /
                                     np.abs(np.real(polo) - np.real(PoloD)))

        #print (np.degrees(angulosPolo))
    # Posteriomente se hace la suma de los angulos de zeros hacia el polo dominante.
    angulosZero = 0
    for zero in G.zero():
        if np.real(zero) > np.real(PoloD):
            angulosZero += np.pi - \
                np.arctan(np.imag(PoloD) /
                          np.abs(np.real(polo) - np.real(PoloD)))
        else:
            angulosZero += np.arctan(np.imag(PoloD) /
                                     np.abs(np.real(polo) - np.real(PoloD)))

    if (accion == "P" or accion == "I") and (angulosPolo - angulosZero) != np.pi:
        print("La accion de control " + accion +
              " no funciona porque no cumple la condicion de fase")
        return 0

    # Y teniendo las dos sumas de angulos, se obtenie el angulo del zero del contralodor PD
    anguloZeroPD = -np.pi + angulosPolo - angulosZero
    # print(np.degrees(anguloZeroPD))
    distanceNewZero = np.real(PoloD) - np.imag(PoloD) / np.tan(anguloZeroPD)

    GcwK = control.TransferFunction([1, -distanceNewZero], [1])
    print("nuevo Polo: {}".format(-distanceNewZero))
    mDen = 1
    mNum = 1
    for polo in (GcwK * G).pole():
        mDen = mDen * mod(polo - PoloD)

    for zero in (GcwK * G).zero():
        mNum = mNum * mod(zero - PoloD)
    k = mDen / (mNum * gain)
    print("k: {}".format(k))

    GcwK = GcwK * k
    print(GcwK * PID)
    Tout, yout = control.step_response(GcwK * G / (GcwK * G + 1))
    rlistO, klistO = control.root_locus(GcwK * G, Plot=False)
    # plt.plot(T,yout)

    # plt.show()

    if accion == "PD":
        Td = 1 / (-distanceNewZero)
        Kp = k / Td
        sal = "k= " + str(k) + " kp= " + str(Kp) + " Td= " + str(Td)
        constantes = {
            'ti': 0,
            'td': Td,
            'kp': Kp
        }
        print(sal)
    elif accion == "PID":
        Td = (1 / (-distanceNewZero - PID.zero()))[0]
        Kp = k / Td
        Ti = (1 / (distanceNewZero * PID.zero() * Td))[0]
        sal = ("k= " + str(k) + " kp= " + str(Kp) +
               " Td= " + str(Td) + " Ti= " + str(Ti))
        print(sal)
        constantes = {
            'ti': Ti,
            'td': Td,
            'kp': Kp
        }

    elif accion == "PI":
        Ti = 1 / (-distanceNewZero)
        Kp = k
        sal = ("k= " + str(k) + " kp= " + str(Kp) + " Ti= " + str(Ti))
        print(sal)
        constantes = {
            'ti': Ti,
            'td': 0,
            'kp': Kp
        }

    else:
        print("No se tiene definicion de la accion de control deseada; las acciones de control definidas son I, P, PI, PD y PID")
        constantes = {
            'ti': 0,
            'td': 0,
            'kp': 0
        }
    return(Tout, yout, sal, Tin, yin, rlistI, rlistO, constantes)


# Diseño de controlador mediante respuesta en frecuencia
# Se necesita saber,"G" la funcion de trasferencia de la planta, la accion de control,
# y los paramentros de comportamiento deseados
# La función regresa los datos para ver graficamente la respuesta
# y los valores de las constantes necesarias para controlar la planta
def controladorByFreq(planta, accion, tr, fase):
    planta = planta.minreal()
    Tin, yin = control.step_response(planta / (planta + 1))
    magIn, phaseIn, omegaIn = control.bode(planta, Plot=False)

    # Se establece una acción de control
    PD = control.TransferFunction([1], [1])
    PI = control.TransferFunction([1], [1, 0])
    PID = control.TransferFunction([1, 2], [1, 0])
    if accion == "PD":
        G = planta * PD
    elif accion == "PI" or accion == "I":
        G = planta * PI
    elif accion == "PID":
        G = planta * PID
    G = G.minreal()
    wc = 10 / tr
    faseR = (fase / 180) * np.pi

    # Se debe conocer la ganacia neta de la funcion de transferencia
    # sin importar como se introdujo la función de trasnferencia
    tfgf = control.TransferFunction([1], [1])  # transfer function gain finder
    for zero in G.zero():
        tfp = control.TransferFunction(
            [1], [1, -1 * zero])  # transfer funtion of prube
        tfgf = tfgf * tfp
    tfg = G * tfgf
    gain = tfg.num[0][0][0]
    print("Gain {}".format(gain))

    # Posteriormente se obtienene los angulos de los polos y lo zeros,
    # tal como dice el metodo de frecuencia, para despues obtener wpd, el td y el kp
    less_than_0_pole = np.array(list(filter(lambda x: x < 0, G.pole() )))
    less_than_0_pole_abs = less_than_0_pole * (-1)
    num_of_poles_equal_0 =len(list(filter(lambda x: x == 0, G.pole())))
    lesss_than_0_zero = np.array(list(filter(lambda x: x < 0, G.zero())))
    lesss_than_0_zero_abs = lesss_than_0_zero * (-1)
    num_of_zeros_equal_0 = len(list(filter(lambda x: x == 0, G.zero())))

    angPoles  = sum(np.arctan(wc / less_than_0_pole_abs)) + 0.5 * np.pi * num_of_poles_equal_0
    angZeros  = sum(np.arctan(wc / lesss_than_0_zero_abs)) + 0.5 * np.pi * num_of_zeros_equal_0
    wpd = wc / (np.tan(faseR - np.pi + angPoles  - angZeros ))
    td = 1 / wpd

    wpdProd = 1
    if wpd<0:
        wpdProd = np.sqrt(wc/(-1 * wpd))
        pass

    prods_of_roots_divided = (np.prod(np.sqrt((wc / less_than_0_pole_abs)**2 + 1)) /
        ((np.prod(np.sqrt(wc / lesss_than_0_zero_abs)) * wpdProd)**2 + 1))
    poles_dividedBy_zeros = np.prod(less_than_0_pole_abs) / (np.prod(-1 * lesss_than_0_zero) * gain)
    wc2_poles_minus_zeros =(wc**num_of_poles_equal_0) / (wc**num_of_zeros_equal_0)

    kp = prods_of_roots_divided * poles_dividedBy_zeros * wc2_poles_minus_zeros
    print(kp)

    # Se obtienen los valores de ti, en caso que se hubiera querido usar un PI
    ti = td
    print(kp * ti)

    # Se hace lo mismo para el PID
    TdPID = 1 / ((wpd) + (-1 * PID.zero()))
    TiPID = 1 / ((wpd) * (-1 * PID.zero()) * TdPID)
    KP_pid = kp / TdPID

    # Se revisa la parte anteriomente desconocida de la  funcion del controlador (sin zeros extras o polos en el origen)
    Gc = kp * control.TransferFunction([1 / wpd, 1], [1])
    print(Gc)
    Tout, yout = control.step_response(G * Gc / (G * Gc + 1))
    magOut, phaseOut, omegaOut = control.bode(G * Gc, Plot=False)

    if accion == "PD":
        sal = " kp= " + str(kp) + " Td= " + str(td)
        print(sal)
        constantes = {
            'ti': 0,
            'td': td,
            'kp': kp
        }
    elif accion == "PID":
        sal = (" kp= " + str(KP_pid[0]) +
               " Td= " + str(TdPID[0]) + " Ti= " + str(TiPID[0]))
        print(sal)
        constantes = {
            'ti': TiPID[0],
            'td': TdPID[0],
            'kp': KP_pid[0]
        }
    elif accion == "PI":
        sal = (" kp= " + str(kp * ti) + " Ti= " + str(ti))
        print(sal)
        constantes = {
            'ti': ti,
            'td': 0,
            'kp': kp * ti
        }
    else:
        print("No se tiene definicion de la accion de control deseada; las acciones de control definidas son I, P, PI, PD y PID")
    return (sal, Tin, yin, Tout, yout, constantes)

# Funcion necesaria para convertir las constantes como Ti, tiempo integrativo,
# en valores propios de la ecuacion de diferencia y poder hacer el control discreto
def setValoresEqDif(constantes, accion, T):
    if accion == "PD":
        Td = constantes['td']
        Kp = constantes['kp']
        kd = Td * Kp
        return({
            "a0": (Kp + kd / T),
            "a1": -kd / T,
            "a2": 0,
            "b0": 0
        })

    elif accion == "PID":
        Td = constantes['td']
        Kp = constantes['kp']
        Ti = constantes['ti']
        kd = Td * Kp
        ki = Kp / Ti
        return ({
            "a0": Kp + ki * T + kd / T,
            "a1": -Kp - 2 * kd / T,
            "a2": kd / T,
            "b0": 1
        })
    elif accion == "PI":
        Kp = constantes['kp']
        Ti = constantes['ti']
        ki = Kp / Ti
        return ({
            "a0": Kp + ki * T,
            "a1": -Kp,
            "a2": 0,
            "b0": 1
        })
    else:
        return ({
            "a0": 0,
            "a1": 0,
            "a2": 0,
            "b0": 0
        })
    print(valoresEqDif)
    return valoresEqDif


app = Flask(__name__)

GPlantaStrInput = '1/1,9.21,19.89,0'
Mp = '9'
Ta = '0.1'
Ts = '0.05'
tr = '8'
fase = '60'
accion = 'PD'
T = 0.05
valoresEqDif = {
    'a0': 0,
    'a1': 0,
    'a2': 0,
    'b0': 0,
}
constantes = {
    "ti": 0,
    "td": 0,
    "kp": 0
}

def setPlanta(PlantaStr):
    Planta = PlantaStr.split("/")
    numerador = [float(i) for i in Planta[0].split(',')]
    if len(Planta) >= 2:
        denominador = [float(i) for i in Planta[1].split(',')]
    else:
        denominador = [1.0]
    return control.TransferFunction(numerador, denominador)

# La siguiente ruta recoge los datos del index.html, donde se encuentra el metodo de LGR,
# los manda las funciones del LGR y regresa los datos para las graficas y las constantes
# de nuevo al index.html
@app.route('/', methods=['GET', 'POST'])
def index():
    webC = {'estado': 'none', 'accion': 'PD'}
    if request.method == 'POST':
        # Then get the data from the form

        global GPlantaStrInput, Mp, Ta, T, constantes, accion, Ts, valoresEqDif

        GPlantaStrInput = request.form['G']
        accion = request.form['action']
        Ta = request.form['ta']
        Mp = request.form['mp']
        Ts = request.form['ts']

        GPlanta = setPlanta(GPlantaStrInput)
        poloD = poloDominante(float(Mp), float(Ta))
        # print(GPlanta)

        #respt = controladorByLGR(GPlanta, accion, -2 + 2.5j)
        if len(Ta) > 0 and len(Mp) > 0 and len(Ts) > 0:
            T = float(Ts)
            if float(Mp) > 0 and float(Ta) > 0:
                to, yo, sal, ti, yi, rI, rO, constantes = controladorByLGR(GPlanta, accion, poloD)
            else:
                # NOTE: No hay tiempos en 0 o menores por lo que solo se ponen unos polos dominantes de referencia
                to, yo, sal, ti, yi, rI, rO, constantes = controladorByLGR(GPlanta, accion, -2 + 2.5j)

        rI = list(zip(*rI))
        realI = np.real(rI)
        imagI = np.imag(rI)
        rO = list(zip(*rO))
        realO = np.real(rO)
        imagO = np.imag(rO)
        webC['estado'] = 'inline'
        webC['accion'] = accion
        valoresEqDif = setValoresEqDif(constantes, accion, T)
        valoresEqDifJson = json.dumps(valoresEqDif)
        print(str(valoresEqDif))


        return render_template('index.html', estado=webC, valoresEqDif=valoresEqDifJson, ta=Ta, mp=Mp, ts=Ts, to=[to.tolist()], yo=[yo.tolist()], planta=GPlantaStrInput, constantes=sal,
                               ti=[ti.tolist()], yi=[yi.tolist()], realI=realI.tolist(), imagI=imagI.tolist(), realO=realO.tolist(), imagO=imagO.tolist())
    else:
        return render_template('index.html', estado=webC, valoresEqDif='', ta=Ta, mp=Mp, ts=Ts, to=[[1, 2, 3]], yo=[[1, 0, 3]], planta=GPlantaStrInput, constantes="",
                               ti=[[1, 1.5, 2]], yi=[[3, 6, 7]], realI=[[2, 3, 1], [4, 2, 3], [9, 6, 2]], imagI=[[4, 5, 3], [4, 8, 9], [3, 1, 0]], realO=[[1, 3]], imagO=[[4, 5]])


# La siguiente ruta recoge los datos de freq.html, donde se encuentra el metodo de frecuencia,
# los manda las funciones de frecuencia y regresa los datos para las graficas y las constantes
# de nuevo a freq.html
@app.route('/freq', methods=['GET', 'POST'])
def freq():
    webC = {'estado': 'none', 'accion': 'PD'}
    if request.method == 'POST':
        # Then get the data from the form
        global GPlantaStrInput, tr, fase, T, Ts

        GPlantaStrInput = request.form['G']
        accion = request.form['action']
        fase = request.form['fase']
        tr = request.form['tr']
        Ts = request.form['ts']

        GPlanta = setPlanta(GPlantaStrInput)
        T = float(Ts)
        #respt = controladorByLGR(GPlanta, accion, -2 + 2.5j)
        if float(tr) > 0 and float(fase) > 0:
            sal, Tin, yin, Tout, yout, constantes = controladorByFreq(
                GPlanta, accion, float(tr), float(fase))
        else:
            # NOTE: No hay tiempos en 0 o menores por lo que solo se ponen unos polos dominantes de referencia
            sal, Tin, yin, Tout, yout, constantes = controladorByFreq(
                GPlanta, accion, 5, 6)

        valoresEqDif = setValoresEqDif(constantes, accion, T)
        webC['estado'] = 'inline'
        webC['accion'] = accion


        return render_template('freq.html', ts=Ts, estado=webC, valoresEqDif=str(valoresEqDif), planta=GPlantaStrInput, tr=tr, fase=fase, constantes=sal, Tin=[Tin.tolist()], yin=[yin.tolist()], Tout=[Tout.tolist()], yout=[yout.tolist()])
    else:
        return render_template('freq.html', ts=Ts, estado=webC, valoresEqDif='', planta=GPlantaStrInput, tr=tr, fase=fase, constantes="", Tin=[[5, 2]], yin=[[6, 3]], Tout=[[7, 4, 1], [6, 9]], yout=[[5, 2, 9], [7.89, 5]])


@app.route('/controlar', methods=['GET', 'POST'])
def usoDeControlador():
    global constantes, accion

    valoresEqDif = setValoresEqDif(constantes, accion, T)
    print(constantes)
    print(accion)
    print(valoresEqDif)
    return render_template('usoDeControlador.html', valoresEqDif=valoresEqDif)

@app.route('/intro', methods=['GET'])
def intro():
    return render_template('intro.html')

if __name__ == '__main__':
    app.run(debug=True)
