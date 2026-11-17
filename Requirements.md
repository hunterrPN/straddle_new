Intern Challenge
Build a BTC Options Straddle Using NautilusTrader
A practical engineering assignment for aspiring engineers joining our trading systems team.
1. The Context
We build quantitative trading systems that operate across financial and derivatives markets. Our technology stack includes NautilusTrader, an event-driven trading engine used for developing, testing, and deploying systematic trading strategies.
As part of this assignment, you will get hands-on experience with NautilusTrader and its Bybit integration.
Your objective is to explore the framework, understand how market data and order execution work, and implement a simple options trading strategy.
You don't need prior experience with NautilusTrader. We expect you to explore the framework, read the documentation, experiment with the examples, and get something working.
2. How Difficult Is This Assignment?
Let's be clear: This is an intentionally simple and introductory assignment.
If you are comfortable with Python, understand the basics of financial markets and options, and can navigate technical documentation, Level 1 should be fairly straightforward.
You do not need advanced quantitative knowledge, sophisticated mathematical models, or years of trading experience to complete this task.
The objective is not to test whether you can run an options strategy on Nautilus Trader.
We are more interested in:
How quickly you can get started.
How effectively you explore an unfamiliar framework.
How you use available resources to solve problems.
Whether you understand the implementation rather than just making it work.
How much initiative and curiosity you demonstrate.

3. Use AI. Explore. Experiment.
You are absolutely free to use AI tools and platforms of your choice. In fact, we encourage it.
You can use:
ChatGPT, Claude, Gemini, or any other LLM.
GitHub Copilot, Cursor, or other AI coding assistants.
Any relevant APIs, SDKs, libraries, and open-source projects.
AI-powered debugging and development tools.
There are no restrictions on which AI platform or LLM you use.
We believe modern engineers should know how to use these tools effectively to accelerate their work.
However, there is one important expectation:
You should understand whatever you submit.
Using AI to generate code is perfectly fine. Being unable to explain what that code does is not.
When we review your assignment, we will ask you to walk us through your implementation and explain the complete execution flow.

4. The Objective
Build and execute a simple BTC ATM Short Straddle strategy using NautilusTrader, connected to Bybit.
A short straddle involves selling:
One ATM Call option.
One ATM Put option.
Both options should have the same strike price and expiry.
The ATM strike should be selected based on the BTC underlying reference price and the available option strikes.
You will implement this strategy in two stages.
5. Level 1 – Build a Naked Straddle
Core assignment
Your task:
Set up NautilusTrader and understand its basic architecture.
Configure and connect to the Bybit integration.
Subscribe to BTC options market data.
Identify the available BTC option contracts.
Determine the nearest ATM strike using the BTC reference price.
Select the corresponding Call and Put contracts with the same strike and expiry.
Submit sell orders for both options.
Track order acknowledgements, executions, and open positions.
Risk Management
For this level:
No Stop-Loss.
No Take-Profit.
No automated exit conditions.
The objective is to get the complete strategy execution flow working and observe how the two short option positions behave as market prices change.
Expected Outcome
A working strategy that can:
Connect to Bybit.
Subscribe to BTC options data.
Identify the ATM strike.
Execute a Call + Put short straddle.
Track the resulting positions and market movements.
6. Level 2 – Add Automated Risk Management
Advanced challenge
Extend your Level 1 strategy by implementing automated risk management.
Parameter
Value
Stop-Loss
1%
Take-Profit
2%

Stop-Loss
If the combined premium required to buy back both options increases by 1% from the combined entry premium, the strategy should automatically close both positions.
Take-Profit
If the combined premium required to buy back both options decreases by 2% from the combined entry premium, the strategy should automatically buy back and close both positions.
For this assignment, calculate the combined premium using both option legs, with consistent contract quantities. Use ask-side quotes for the buyback valuation.
Your strategy should continuously monitor the combined straddle value and trigger the appropriate exit condition.
Expected Outcome
A complete BTC short-straddle strategy with:
Automated Stop-Loss.
Automated Take-Profit.
Position monitoring.
Appropriate closing orders.
Handling of partially executed orders and duplicate exit attempts.
A Little Extra Motivation
Candidates who successfully complete Level 2 and can demonstrate their implementation to us have a special surprise waiting for them!
We won't reveal it just yet. :)

7. The Most Important Part: Walk Us Through Your Implementation
Once you have completed the assignment, we would like you to schedule a short walkthrough with our engineering team.
This is an important part of the assignment.
We want you to demonstrate that you understand what you have built and can explain the entire flow.
For example:
How does NautilusTrader start and initialize?
How have you configured the Bybit integration?
How does NautilusTrader receive market data?
How are BTC option instruments identified and subscribed to?
How does the strategy receive market data events?
How are orders submitted to Bybit?
How does the system know whether an order was accepted or executed?
How are positions tracked?
How have you implemented the Stop-Loss and Take-Profit?
What happens when one leg gets executed but the other leg does not?
You don't need to know every internal detail of the NautilusTrader framework. And we have given you these 10 points in writing so your LLM also helps you achieve the task in accordance with ;)
We are interested in your understanding, not just your ability to generate working code.

8. What You Need to Submit
Basically nothing - Just demonstrate your implementation on a meet call and explain the execution flow to our engineering team :)

9. What If You Get Stuck?
This is important.
We do not expect everyone to complete the entire assignment.
We understand that NautilusTrader may be unfamiliar to you and that connecting to a new trading framework can involve a learning curve.
Even if you cannot complete the assignment, we would still appreciate seeing:
You can even walk us through an incomplete implementation.
A clear explanation of a problem, the debugging you attempted, and your thought process is much more valuable to us than code copied from somewhere without understanding it.
We would much rather have a candidate who reaches 40% of the assignment through genuine effort and can explain what he has done/understood.

10. What We Are Looking For
This assignment is also an opportunity for us to understand how you approach engineering problems.
We value:
Curiosity: Are you interested in understanding how things work?
Initiative: Can you explore documentation and find solutions independently?
Problem-solving: How do you approach something that isn't working?
Ownership: Do you take responsibility for completing what you start?
Communication: Can you clearly explain what you built and where you need help?
Genuine interest: Are you excited about building real trading systems, or are you simply looking for an internship certificate?
We don't expect you to be an expert. We do expect you to be genuinely interested.

11. Useful Resources
NautilusTrader Documentation: https://nautilustrader.io/docs/latest/
Bybit Integration: https://nautilustrader.io/docs/latest/integrations/bybit/
Understanding a Straddle: https://www.investopedia.com/terms/s/straddle.asp
NautilusTrader GitHub: https://github.com/nautechsystems/nautilus_trader
You are encouraged to explore the examples, documentation, source code, and AI tools.

12. A Final Note
We are building real products and trading systems, and we want people who enjoy the process of building them.
This assignment is a small glimpse of the kind of engineering problems you will encounter during the internship.
Don't worry about getting everything right on the first attempt.
Experiment, use AI, break things, debug, learn, and keep moving.
We are interested in how you think, how you approach challenges, how you use the resources available to you, and how much initiative you take.
Happy building!
The Engineering Team






Help
You can connect with ByBit using their TestNet accounts
