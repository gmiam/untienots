# Cloud/DevOps Technical Test - Result

This is a walkthrough of what has been done to meet the requirements of this exercice. We can consider this as a readme as following these instruction will give a working example. But this is also a place used to discuss what is not optimal and what can be imagine to go further.

To follow all the commands listed below, you will need to first clone this repository. Once done, you can use them as is if you're in the root directory of the repo.

## Deploying to kubernetes

The goal here is to deploy a Python API to kubernetes. So first we need to build a docker image.

### Prerequisite - Building a docker image for fastapi (Python framework)

We aim at keeping the docker file as simple as possible for multiple reasons.

* Security: we need to be able to quickly understand each line of the Dockerfile in order to be sure what will contain the image we will deploy
* No configuration built-in in the image. For a deployment in kubernetes we will need to be able to manage configuration dynamically, for example to reach the right mongodb database for the current environment

We will discuss this matter a bit more later so we'll stop here for now.
Here is the Dockerfile we will use in this exercise

```
FROM python:3.7

RUN pip install fastapi uvicorn python-dotenv pymongo

COPY ./app /app

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "80"]
```

We start with a python base image (we will discuss this later). We install the depencies we need and that are not included in the base image.

We copy the app folder containing the fastapi code in the container. We can notice here that we don't copy the .env file in this docker image. We'll get back to that later. 
* Note: we modified the app/\_\_init__.py file provided by modifying the env_file variable from .env to config/.env - more on this later (the change have been reflected in this repository)

We then use CMD to launch our application at container startup.

For the purpose of this exercise we will publish this image using dockerhub. 

We first create a directory containing this Dockerfile and the app folder (we can obtain such directory by cloning this git repository). Then we use the following commands:
```
docker build -t gmiamz/untienots:0.4 . // Create the docker image locally and tag it
docker push gmiamz/untienots:0.4 // push the docker image to the dockerhub repository
```

### Prerequisite - Build your own kubernetes cluster

In our case we need to have a kubernetes cluster, but we don't need it to be production ready (yet). So we use the k3s distribution which allow to build very quickly a kubernetes cluster and providing by default an Traefik based ingress.

* Traefik is a reverse proxy which can natively be used as kubernetes ingress
* Kubernetes ingress is the object which is used to expose HTTP(s) endpoint for clients outside our cluster.

Installation is very very simple:

```
curl -sfL https://get.k3s.io | sh -
```
Note that piping the result of a curl directly in a shell is strongly not recommended (see [for example](https://www.idontplaydarts.com/2016/04/detecting-curl-pipe-bash-server-side/))

And... that's it!

### Prerequisite - Install mongodb in kubernetes

For the purpose of this exercise we want to install mongodb directly inside our kubernetes cluster. While this may be very challenging to do in production it actually makes sense to be able to have a self contained environment for development needs.

We will use the [community mongodb operator](https://github.com/mongodb/mongodb-kubernetes-operator.git) to do this. This will install an operator in charge of maintaining the statefulset which will provide the mongod themselves (3 by default) but will also provide capabilities to create users and assign roles and permissions to them.

All the files we will use in order to create this mongodb cluster + operator and any other related resources are located in the mongodb folder of this git repository. All the values used in this example are harcoded in those files. But we will highlight here what we did that is not explicitly in the official documentation of the operator.

```
kubectl create ns mongodb // we create a dedicated namespace for the database
// we create the custom resource definitions used by the operator
kubectl apply -f mongodb/mongodbcommunity.mongodb.com_mongodbcommunity.yaml 
// we create all the roles and permissions fot the custom resources
kubectl apply -f mongodb/role.yaml -n mongodb
kubectl apply -f mongodb/role_binding.yaml -n mongodb  
kubectl apply -f mongodb/service_account.yaml -n mongodb  
// deployment for the mongo operator itself
kubectl create -f mongodb/manager.yaml -n mongodb
// We create the user we will use with its password and roles/permissions
kubectl apply -f mongodb/mongodb.com_v1_mongodbcommunity_cr.yaml -n mongodb  (user, role and password)
```

* Note: For this last file, the password is hardcoded in it (it is possible to delete the secret once the user is created), and we add a role readWriteAnyDatabase on the default db admin. We recommend to check the detail of this file for a better understanding. This is not optimal on a security standpoint, but rbac fine tuning has been considered out of scope of this exercise

After this we should have an operator pod up and running alongside three mongodb pods managed by a statefulset.

### Deploy our API in our cluster

First we create a configmap based on the .env file provided. This will be used to mount the config file as a volume/file inside the container of our applicative pod.

We can notice that the mongodb url is now: mongodb://admin:my-secure-password@example-mongodb-svc.mongodb.svc.cluster.local:27017/?replicaSet=example-mongodb

This reflect our new mongodb deployment:
* admin is the user we created
* my-secure-password is the password we associated with this user
* example-mongodb-svc is the name of the kubernetes service created for the database
* mongodb is the name of the namespace in which we deployed our database
* .svc.cluster.local is the domain of the kubernetes network, this is mandatory for the DNS resolution inside the cluster
* 27017 is the default mongodb port and we keep it as is
* The last part is the default replicaSet (mongodb meaning, not kube) created by the operator

```
kubectl -n untienots create configmap dotenv --from-file=.env
```

We then create our deployment (which will manage our applicative pod) and an associated service to make the pod easily reachable for other services deployed in the cluster.

Here is the file used to define those objects:
```
apiVersion: apps/v1
kind: Deployment
metadata:
  name: untienots
  labels:
    app: untienots
spec:
  replicas: 1
  selector:
    matchLabels:
      app: untienots
  template:
    metadata:
      labels:
        app: untienots
    spec:
      containers:
      - args:
        name: untienots
        image: gmiamz/untienots:0.4 // The docker image we retrieve from dockerhub
        imagePullPolicy: IfNotPresent
        ports:
        - containerPort: 80
          name: http-api
          protocol: TCP
        volumeMounts: // we mount the file .env in /config/ based on the volume dot env below 
        - mountPath: /config 
          name: dotenv
          readOnly: true
      volumes:  // We define the volume based on the configmap we created
      - configMap:
          name: dotenv
        name: dotenv
---
apiVersion: v1
kind: Service
metadata:
  name: untienots-svc
spec:
  ports:
  - name: http
    port: 80
    protocol: TCP
    targetPort: 80
  selector:
    app: untienots
  sessionAffinity: None
  type: ClusterIP
```

Based on this file, we can deploy.
```
kubectl -n untienots apply -f kube/untienots.yaml
```

It's now time to check that everything is working as intended

```
root@ip-172-31-1-66:/home/ubuntu# kubectl -n untienots get svc
NAME            TYPE        CLUSTER-IP    EXTERNAL-IP   PORT(S)   AGE
untienots-svc   ClusterIP   10.43.18.32   <none>        80/TCP    8s
// We will use the cluster-ip of the service to call the API from the host server
root@ip-172-31-1-66:~# curl -L http://10.43.18.32/users
[]
root@ip-172-31-1-66:~# curl -L -X POST http://10.43.18.32/users -d '{"name": "test-name", "username": "test-username", "email" : "username@email.com"}'
root@ip-172-31-1-66:~# curl -L http://10.43.18.32/users
[{"_id":"608807ffaccf71c7ca4c9791","name":"test-name","username":"test-username","email":"username@email.com"}]
```

It works!

We were able to check that there was no users in the database. We were then able to create a user and to retrieve it and all of this using only the API.

* Note: at this point, everything is full HTTP, no encryption. This is not necessarily a problem yet as we don't expose anything over internet. Also this is not always an anti-pattern regarding kubernetes deployments as we can use a service mesh (istio/linkerd/...) to add a sidecar to the pod. This deployment pattern let the applicative container expose HTTP while the pod will expose HTTPS only. This also let the developpers to not have to handle anything related to encryption and in the same time this allow us to be 100% sure that everything is HTTPS. More on this later.


## Moving to production

We have now our API working in a development environment and we have a lot more ton consider before being able to use it in production. In this section we will answer the questions.

**Q1/ We need to provision a DNS domain and SSL Certificates for our API in production, what tools can we use to automate that process? Can you explain how they work?**

In order to use an API in production, we need to be able to expose it over internet. We need also to have a nice public DNS domain and alias. Assuming we will run our kubernetes cluster over a public cloud provider such as GCP or AWS, we consider the DNS objects as infrastructure. As all our infrastructure, we want it defined as code.

The major tool used to do that is Terraform. Terraform is composed of a CLI and a delarative language (HCL). Using it we are able to declare all our infrastructure in declarative file, using the proprietary HCL language. Terraform maintain also a state for each project (by default in a *.tfstate file). And each time we use the cli in our project, Terraform will refresh its internal state comparing the actual infrastructure and the tfstate file. Base on that comparison, it will ouput all the changes that need to be made in order to have the infrastructure matching the declarative file. In order to do so, Terraform use the APIs of the main cloud provider (but also other connector such as VMware or kubernetes itself).

Everything Terraform use to create or modify resources is publicly available through apis or cli coming from vendor themselves (AWS even have its own cli and its own infrastructure as code: CloudFormation). The value of terraform is in its maturity and in the possibility to reuse some part of the code between different provider (it can be very tricky though).

* Note: there is a newcomer in this market: Pulumi. Its particularity is to rely on mainstream language to describe the infrastructure (python, go, typescript, ...). This is an interesting approach as a lot of people know these languages and it also allow to perform unit testing on Pulumi code. (Disclaimer: I never tried to use it yet)

Once we have a public endpoint we need to securize it. The first thing we may think about is to encrypt all the traffic between clients and the server. To do that we use HTTPS (or HTTP over TLS). We now have a great tool to automate that (and this is important as certificate expiration remain a large source of unavailability): Let's Encrypt. It allows to provide TLS certificates at the domain validation (DV) level. Indeed it is impossible to automate Organization validation (OV) or Extended validation (EV) levels as they require explicit human interractions. Though DV level is just as secure as the others at a technical level, the difference lies in the authentication of the organization behind the domain name, but let's forget that.

Let's encrypt can be set up to be used with proxies such as nginx or traefik for example. It will issue a challenge to verify that the requester is indeed the owner of the domain for which it requests a certificate (preventing to usurp the identity of another domain).
It will emit a certificate valid for three months and its integration with this kind of proxies will allow an automatic renewal few days before expiration.


**Q2/ How can we make sure that our Docker images running in production are secure? What security risks are we exposed to if we run any images we find in production?**

The use of secure docker images in production is a major concern. Indeed we don't have the same isolation level as we have using virtual machines so in the worst case scenario a container is fully compromised and can be used to spy on other processes on the host (eventually other containers).
The first reflex to have is to check the base image we use. I usually recommend to use Google's distroless image which are well hardenized. I didn't use it during the exercise because it would have required a bit of rework around the dependancies installation and this seemed a bit out of scope. Also we need to check precisely every layer we had on the base image to make sure we understand and eventually control eveyrhtin we add.
It is also a good practice to scan the images we build in the CI/CD chain with tools like Clair or Anchore.

The risks we face running non secure docker images in production are many.
* We can have a compromised container as describe earlier.
* We can have a process spying on the traffic and forwarding traffic outside (even though it can be mitigated)
* We can face performance issue because of other processes running inside the container or having unnecessary huge image which can impact the whole platform in term of performance and cost
* We even have seen some docker images which were used to mine cryptocurrencies...

**Q3/ This API and it's database handles sensible data, what security measure can we implement to isolate them from other applications? How would you limit the risk of data exfiltrations? Improve your Kubernetes deployment to take into account those security measures, and deploy it to your cluster.**

For this kind of need I would recommend the use of a service mesh such as istio or linkerd. These tools will deploy a sidecar container to the pod. The pod will then have two containers and one will be a proxy (envoy for istio or specific for linkerd). The service-mesh will also trick the iptables of the pod to make sure all traffic in and out will (transparently) go through the proxy.

The proxy will then be able to perform some control or modification on the traffic. For example enforce automatically mTLS between two sidecar proxies (traffic inside the cluster kubernetes) or enforce (m)TLS on an outgoing HTTP call based on configuration or also make sure the destination of an outgoing request is valid, including requests trying to reach a database.

There are also tools such as Cilium based on the new eBPF capabilities of the Linux kernel that override all the network stack of Kubernetes (not based on iptables) and being much more performant and also providing a fine-grained control over which pod is allowed to reach a specific pod.

As the only way to reach a pod in a kubernetes cluster should be to go through an ingress (hence a pod), this allow to very precisely control all the traffic going in and out the cluster in addition of controlling the cluster inside the cluster.


## Migrate a Kubernetes Cluster
